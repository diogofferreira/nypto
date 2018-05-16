import numpy as np
import scipy.stats as stats
import matplotlib.pyplot as plt
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
import sys
import warnings
import scalogram

warnings.filterwarnings('ignore')


def wait_for_enter(fstop=True):
    if fstop:
        if sys.version_info[0] == 2:
            input("Press ENTER to continue.")
        else:
            input("Press ENTER to continue.")
            

def plot_traffic_class(data, name):
    plt.plot(data)
    plt.title(name)
    wait_for_enter()


def plot_3_classes(data1, name1, data2, name2, data3, name3):
    plt.subplot(3, 1, 1)
    plt.plot(data1)
    plt.title(name1)
    plt.subplot(3, 1, 2)
    plt.plot(data2)
    plt.title(name2)
    plt.subplot(3, 1, 3)
    plt.plot(data3)
    plt.title(name3)
    plt.show()
    wait_for_enter()


def get_obs_classes(n_obs_windows, n_elems, traffic_classes):
    return np.vstack([np.ones((n_obs_windows, n_elems)) * t for t in traffic_classes])


def plot_features(features, traffic_classes, feature1_idx=0, feature2_idx=1):
    n_obs_windows, n_features = features.shape
    obs_classes = get_obs_classes(
        int(n_obs_windows / len(traffic_classes)), 1, traffic_classes)
    colors = ['b', 'g', 'r']

    for i in range(n_obs_windows):
        plt.plot(features[i, feature1_idx], features[i, feature2_idx],
                 'o' + colors[int(obs_classes[i])])

    plt.show()
    wait_for_enter()


def break_train_test(data, obs_window=240, slide_window=40,
                     train_percentage=0.5, random_split=True):
    window_size = int(obs_window / slide_window)
    n_samples, n_cols = data.shape
    n_obs_windows = int((n_samples - obs_window) / slide_window)
    n_samples = (n_obs_windows - 1) * slide_window + obs_window
    n_slide_windows = n_obs_windows + window_size - 1
    data = data[:n_samples, :]

    data_slices = data.reshape((n_slide_windows, slide_window, n_cols))
    data_obs = np.array([np.concatenate(data_slices[i:window_size+i], axis=0)
                         for i in range(n_obs_windows)])

    order = np.random.permutation(n_obs_windows) \
        if random_split else np.arange(n_obs_windows)

    n_train_windows = int(n_obs_windows * train_percentage)
    data_train = data_obs[order[:n_train_windows], :, :]
    data_test = data_obs[order[n_train_windows:], :, :]

    return data_train, data_test


def extract_features(data):
    percentils = [75, 90, 95]
    n_obs_windows, n_samples, n_cols = data.shape
    features = np.array([np.hstack((
        np.mean(data[i, :, :], axis=0),
        np.median(data[i, :, :], axis=0),
        np.std(data[i, :, :], axis=0),
        stats.skew(data[i, :, :]),
        stats.kurtosis(data[i, :, :]),
        np.array(np.percentile(data[i, :, :], percentils, axis=0)).T.flatten(),
    )) for i in range(n_obs_windows)])
    
    return features


def extract_silence(data, threshold=256):
    s = [1] if data[0] <= threshold else []

    for i in range(1, len(data)):
        if data[i] <= threshold:
            if data[i-1] > threshold:
                s.append(1)
            elif data[i-1] <= threshold:
                s[-1] += 1

    return s if s != [] else [0]


def extract_features_silence(data):
    features = []
    n_obs_windows, n_samples, n_cols = data.shape
    # Rebenta caso o threshold the silêncio seja 0

    for i in range(n_obs_windows):
        silence_features = np.array([])
        for c in range(n_cols):
            silence = extract_silence(data[i, :, c], threshold=250)
            silence_features = np.append(
                silence_features, [np.mean(silence), np.var(silence)])

        features.append(silence_features)

    return np.array(features)


def extract_features_wavelet(data, scales=[2, 4, 8, 16, 32]):
    features = []
    n_obs_windows, n_samples, n_cols = data.shape

    for i in range(n_obs_windows):
        scalogram_features = np.array([])
        for c in range(n_cols):
            scalo, scales = scalogram.scalogramCWT(data[i, :, c], scales)
            scalogram_features = np.append(scalogram_features, scalo)

        features.append(scalogram_features)

    return np.array(features)


def traffic_profiling(dataset_path, traffic_class, plot=True):
    dataset = np.loadtxt(dataset_path)

    if plot:
        plot_traffic_class(dataset, traffic_class)

    scales = [2, 4, 8, 16, 32, 64, 128, 256]
    data_train, data_test = break_train_test(dataset, random_split=False)
    features = extract_features(data_train)
    test_features = extract_features(data_test)
    features_silence = extract_features_silence(data_train)
    test_features_silence = extract_features_silence(data_test)
    features_wavelet = extract_features_wavelet(data_train, scales)
    test_features_wavelet = extract_features_wavelet(data_test, scales)
    n_obs_windows = data_train.shape[0]

    return features, features_silence, features_wavelet, test_features, \
           test_features_silence, test_features_wavelet, n_obs_windows


def normalize_features(features, test_features):
    scaler = StandardScaler()
    normalized_features = scaler.fit_transform(features)
    normalized_test_features = scaler.fit_transform(test_features)

    pca = PCA(n_components=3, svd_solver='full')
    normalized_pca_features = pca.fit(normalized_features).\
        transform(normalized_features)
    normalized_pca_test_features = pca.fit(normalized_test_features).\
        transform(normalized_test_features)

    return normalized_pca_features, normalized_pca_test_features


def extract_traffic_features(traffic_classes, datasets_filepath):
    if len(traffic_classes) == 0 \
            or len(traffic_classes) != len(datasets_filepath):
        return None

    features = None
    features_silence = None
    features_wavelet = None
    test_features = None
    test_features_silence = None
    test_features_wavelet = None
    n_obs = None

    for d_idx in datasets_filepath:
        d = datasets_filepath[d_idx]
        f, fs, fw, tf, tfs, tfw, n_obs = \
            traffic_profiling(d, traffic_classes[d_idx], False)
        f = f[:184]
        fs = fs[:184]
        fw = fw[:184]
        tf = tf[:184]
        tfs = tfs[:184]
        tfw = tfw[:184]

        if features is None:
            features = np.array([f])
            features_silence = np.array([fs])
            features_wavelet = np.array([fw])
            test_features = np.array([tf])
            test_features_silence = np.array([tfs])
            test_features_wavelet = np.array([tfw])
        else:
            features = np.vstack((features, [f]))
            features_silence = np.vstack((features_silence, [fs]))
            features_wavelet = np.vstack((features_wavelet, [fw]))
            test_features = np.vstack((test_features, [tf]))
            test_features_silence = np.vstack((test_features_silence, [tfs]))
            test_features_wavelet = np.vstack((test_features_wavelet, [tfw]))

    """
    print('Train Stats Features Size:', features.shape)
    plt.figure(4)
    plot_features(features, traffic_classes, 0, 2)

    print('Train Silence Features Size:', features_silence.shape)
    plt.figure(5)
    plot_features(features_silence, traffic_classes, 0, 2)
    """

    # Training features
    all_features = np.dstack((features, features_silence))
    all_features = all_features.reshape(
        all_features.shape[0] * all_features.shape[1],
        all_features.shape[2])

    # Testing features
    all_test_features = np.dstack((test_features, test_features_silence))
    all_test_features = all_test_features.reshape(
        all_test_features.shape[0] * all_test_features.shape[1],
        all_test_features.shape[2])

    # Normalize train and test features
    norm_pca_features, norm_pca_test_features = normalize_features(all_features,
                                                         all_test_features)

    return traffic_classes, norm_pca_features, \
           norm_pca_test_features, n_obs


def profiling():
    traffic_classes = {
        0: 'YouTube',
        # 1: 'Netflix',
        1: 'Browsing',
        # 3: 'Social Networking',
        # 4: 'Mining (Neoscrypt - 4T CPU)',
        # 5: 'Mining (Neoscrypt - 2T CPU)',
        # 6: 'Mining (EquiHash - 65p GPU)',
        # 7: 'Mining (EquiHash - 85p GPU)',
        # 8: 'Mining (EquiHash - 100p GPU)',
    }

    datasets_filepath = {
        0: 'datasets/youtube.dat',
        #1: 'datasets/netflix.dat',
        1: 'datasets/browsing.dat',
        # 3: 'datasets/social-network.dat',
        # 4: 'datasets/mining_4t_nicehash.dat',
        # 5: 'datasets/mining_2t_nicehash.dat',
        # 6: 'datasets/mining_gpu_nicehash_equihash_1070_60p.dat',
        # 7: 'datasets/mining_gpu_nicehash_equihash_1080ti_85p.dat',
        # 8: 'datasets/mining_gpu_nicehash_equihash_1080ti_100p.dat',
    }
    plt.ion()

    return extract_traffic_features(traffic_classes, datasets_filepath)


if __name__ == '__main__':
    profiling()
