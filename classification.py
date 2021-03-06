from sklearn import svm
from sklearn.cluster import DBSCAN
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.externals import joblib
from sklearn.metrics import confusion_matrix
from sklearn.neural_network import MLPClassifier
from scipy.stats import multivariate_normal
from collections import Counter
import numpy as np
import pickle
import argparse
import profiling


def get_centroids(traffic_classes, obs_classes, features):
    centroids = {t: np.mean(features[(obs_classes == t).flatten(), :], axis=0)
                 for t in traffic_classes}
    return centroids


def get_covariances(traffic_classes, obs_classes, features):
    centroids = {t: np.cov(features[(obs_classes == t).flatten(), :], rowvar=0)
                 for t in traffic_classes}
    return centroids


def distance(centroid, point):
    return np.sqrt(np.sum(np.square(point - centroid)))


def classification_distances(centroids, test_features):
    n_obs, n_features = test_features.shape
    traffic_idx = {}

    for i in range(n_obs):
        w = test_features[i]
        distances = [distance(w, centroids[c]) for c in centroids]
        t_idx = np.argsort(distances)[0]
        traffic_idx[i] = t_idx

    return traffic_idx


def classification_gaussian_distribution(traffic_classes, obs_classes, pca_features,
                                         test_pca_features):
    n_obs, n_features = test_pca_features.shape
    means = get_centroids(traffic_classes, obs_classes, pca_features)
    covs = get_covariances(traffic_classes, obs_classes, pca_features)
    traffic_idx = {}

    for i in range(n_obs):
        w = test_pca_features[i, :]
        probs = np.array([multivariate_normal.pdf(w, means[t], covs[t])
                          for t in traffic_classes])
        t_idx = np.argsort(probs)[-1]
        traffic_idx[i] = t_idx

    return traffic_idx


def classification_clustering(traffic_classes, obs_classes, norm_pca_features,
                              norm_pca_test_features, n_clusters=3, eps=10000,
                              method=0):
    traffic_idx = {}
    n_obs, n_features = norm_pca_features.shape
    centroids = np.array([])

    for c in range(n_clusters):
        centroids = np.append(centroids, np.mean(
            norm_pca_features[(obs_classes == c).flatten(), :], axis=0))

    centroids = centroids.reshape((n_clusters, n_features))

    cluster_method = KMeans(init=centroids, n_clusters=n_clusters) \
        if method == 0 else DBSCAN(eps=eps)
    cluster_method.fit(norm_pca_features)
    labels = cluster_method.labels_

    # Determines and quantifies the presence of each original class observation
    #  in each cluster
    clusters = np.zeros((n_clusters, n_features))
    for cluster in range(n_clusters):
        aux = obs_classes[(labels == cluster)]
        for c in range(n_features):
            clusters[cluster, c] = np.sum(aux == c)

    cluster_probs = clusters / np.sum(clusters, axis=1)[:, np.newaxis]

    for i in range(norm_pca_test_features.shape[0]):
        x = norm_pca_test_features[i, :].reshape((1, n_features))
        label = cluster_method.predict(x)
        t_probs = 100 * cluster_probs[label, :].flatten()
        t_idx = np.argsort(t_probs)[-1]
        traffic_idx[i] = t_idx

    return traffic_idx


def classification_random_forests(new_model, obs_classes, norm_features, 
                                  norm_test_features, max_depth=2):
    traffic_idx = {}

    if new_model:
        # Save model
        clf = RandomForestClassifier(max_depth, random_state=0)
        clf.fit(norm_features, obs_classes)
        joblib.dump(clf, 'classification-model/classification_model_rf.sav')
    else:
        # Load model
        clf = joblib.load('classification-model/classification_model_rf.sav')

    result = clf.predict(norm_test_features)

    for i in range(norm_test_features.shape[0]):
        traffic_idx[i] = result[i]

    return traffic_idx


def classification_svm(new_model, obs_classes, norm_features,
                       norm_test_features, mode=0):
    traffic_idx = {}

    modes = {
        0: {'name': 'SVC', 'func': svm.SVC(kernel='linear')},
        1: {'name': 'Kernel RBF', 'func': svm.SVC(kernel='rbf')},
        2: {'name': 'Kernel Poly', 'func': svm.SVC(kernel='poly', degree=2)},
        3: {'name': 'Linear SVC', 'func': svm.LinearSVC()}
    }

    if new_model:
        # Save model
        modes[mode]['func'].fit(norm_features, obs_classes)
        joblib.dump(modes[mode]['func'], 
                    'classification-model/classification_model_svm.sav')
    else:
        # Load model
        modes[mode]['func'] = \
                joblib.load('classification-model/classification_model_svm.sav')

    result = modes[mode]['func'].predict(norm_test_features)
    
    for i in range(norm_test_features.shape[0]):
        traffic_idx[i] = result[i]

    return traffic_idx


def classification_silence(norm_test_features):
    traffic_idx = {}

    # Load model
    clf = joblib.load('classification-model/classification_model_svm_silence.sav')

    result = clf.predict(norm_test_features)

    for i in range(norm_test_features.shape[0]):
        traffic_idx[i] = result[i]

    return traffic_idx


def classification_neural_networks(new_model, obs_classes, norm_pca_features,
                                   norm_pca_test_features, alpha=0.1,
                                   max_iter=100000, hidden_layer_size=1000):
    traffic_idx = {}

    if new_model:
        clf = MLPClassifier(
            solver='sgd',
            alpha=alpha,
            hidden_layer_sizes=(hidden_layer_size,),
            max_iter=max_iter
        )
        clf.fit(norm_pca_features, obs_classes)

        # Save model
        joblib.dump(clf, 'classification-model/classification_model.sav')
    else:
        clf = joblib.load('classification-model/classification_model.sav')


    result = clf.predict(norm_pca_test_features)

    for i in range(norm_pca_test_features.shape[0]):
        traffic_idx[i] = result[i]

    return traffic_idx


def classify_aggregation_window(window, threshold=0.55):
    num_class = {k: v for k,v in Counter(window).items()}
    max_repetition = max(num_class, key=num_class.get)

    if num_class[max_repetition] / len(window) > threshold:
        return [max_repetition for i in range(len(window))]

    return window


def improve_classification_history(traffic_samples, traffic_idx, window_size=40, 
                                   threshold=0.60):
    traffic_idx = list(traffic_idx.values())

    # Use historic view to classify windows
    for ts in traffic_samples:
        i = 0
        while i + window_size < ts:
            c = classify_aggregation_window(traffic_idx[i:i+window_size], 
                                            threshold)
            traffic_idx[i:i+window_size] = c
            i += window_size

        if ts - i > 0:
            c = classify_aggregation_window(traffic_idx[i:ts], threshold)
            traffic_idx[i:ts] = c

    return traffic_idx


def binary_scores(conf_matrix, change_class, max_class):
    tp = conf_matrix[0:change_class, 0:change_class].sum()
    fn = conf_matrix[change_class:max_class+1, 0:change_class].sum()
    fp = conf_matrix[0:change_class, change_class:max_class+1,].sum()
    tn = conf_matrix[change_class:max_class+1, change_class:max_class+1].sum()
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    accuracy = (tp + tn) / (tp + fp + fn + tn)

    return tp, fn, fp, tn, precision, recall, accuracy


def classify_live_data(norm_pca_features):
    model = joblib.load('classification-model/classification_model.sav')
    result = model.predict(norm_pca_features)

    not_mining = len([r for r in result if r < 7])
    classes = {
        'nmin': not_mining / len(result),
        'min': (len(result) - not_mining) / len(result)
    }
    return classes


def print_cm(cm, labels, hide_zeroes=False, hide_diagonal=False, hide_threshold=None):
    """pretty print for confusion matrixes"""
    columnwidth = max([len(x) for x in labels] + [5])  # 5 is value length
    empty_cell = " " * columnwidth
    # Print header
    print("    " + empty_cell, end=" ")
    for label in labels:
        print("%{0}s".format(columnwidth) % label, end=" ")
    print()
    # Print rows
    for i, label1 in enumerate(labels):
        print("    %{0}s".format(columnwidth) % label1, end=" ")
        for j in range(len(labels)):
            cell = "%{0}.1f".format(columnwidth) % cm[i, j]
            if hide_zeroes:
                cell = cell if float(cm[i, j]) != 0 else empty_cell
            if hide_diagonal:
                cell = cell if i != j else empty_cell
            if hide_threshold:
                cell = cell if cm[i, j] > hide_threshold else empty_cell
            print(cell, end=" ")
        print()


def print_results(confusion_matrix, mining_idx_start, mining_idx_end):
    # Compute performance scores
    tp, fn, fp, tn, precision, recall, accuracy = binary_scores(
            confusion_matrix, mining_idx_start, mining_idx_end)

    print('True positives = ', tp)
    print('False negatives = ', fn)
    print('False positives = ', fp)
    print('True negatives = ', tn)
    print('Precision = ', precision)
    print('Recall = ', recall)
    print('Accuracy = ', accuracy)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--profile', action='store_true', default=False,
            help='generate new profiling data (default: false)')
    parser.add_argument('-c', '--classification', action='store_true', 
            default=False, help='generate new classification model (default:false)')
    parser.add_argument('-m', '--method', nargs='?', default=0, type=int,
            help='classification method - 0:Multimethod | 1:SVM | 2: NN (default: 0)')
    args = parser.parse_args()

    if args.profiling:
        # Generate new profiled data
        unnorm_train_features, unnorm_test_features, \
        norm_pca_train_features, norm_pca_test_features, \
        traffic_classes, traffic_samples_number = profiling.profiling()

        # Save profiling data
        d = {
            'unnorm_train': unnorm_train_features,
            'unnorm_test': unnorm_test_features,
            'norm_train': norm_pca_train_features,
            'norm_test': norm_pca_test_features,
            'classes': traffic_classes,
            'samples_number': traffic_samples_number
        }

        with open('profiled-data/input_data.pkl', 'wb') as output:
            pickle.dump(d, output, pickle.HIGHEST_PROTOCOL)

    else:
        # Load saved profiled data
        with open('profiled-data/input_data.pkl', 'rb') as input:
            d = pickle.load(input)

        unnorm_train_features = d['unnorm_train']
        unnorm_test_features = d['unnorm_test']
        norm_pca_train_features = d['norm_train']
        norm_pca_test_features = d['norm_test']
        traffic_classes = d['classes']
        traffic_samples_number = d['samples_number']

    obs_classes = profiling.get_obs_classes(traffic_samples_number, 1,
                                            traffic_classes)

    # Plot unnormalized features
    #profiling.plot_features(unnorm_train_features, traffic_classes)

    if args.method == 0:
        # Classify using two models
        # First default model
        y_test_model1 = classification_random_forests(
                args.classification, obs_classes, norm_pca_train_features,
                norm_pca_test_features, max_depth=2)

        # Perform window aggregation
        y_test_model1 = improve_classification_history(
                traffic_samples_number, y_test_model1)

        possible_mining = [i for i, x in enumerate(y_test_model1) if x >= 13]

        # Silence model
        y_test_model2 = classification_silence(norm_pca_test_features[:, 24:32])

        y_test = [y_test_model2[i] if i in possible_mining else y_test_model1[i]
                  for i in range(len(y_test_model1))]

    elif args.method == 1:
        # Classify using SVM
        y_test = classification_svm(args.classification, obs_classes, 
                                    norm_pca_train_features,
                                    norm_pca_test_features, mode=0)
        y_test = improve_classification_history(traffic_samples_number, y_test)

    elif args.method == 2:
        # Classify using NN
        y_test = classification_neural_networks(
                args.classification, obs_classes, 
                norm_pca_train_features, norm_pca_test_features)
        y_test = improve_classification_history(traffic_samples_number, y_test)

    cm = confusion_matrix(obs_classes, y_test)
    print_results(cm, 13, 31)



if __name__ == '__main__':
    main()
