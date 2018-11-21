import tensorflow as tf
import os, sys
import h5py
import gcn.utils
from scipy.sparse import lil_matrix
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import math
from deepexplain.tensorflow import DeepExplain
sys.path.append(os.path.abspath('../GCN'))
from my_gcn import MYGCN
import utils
from time import time
import argparse


def str_to_num(s):
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return s


def load_hyper_params(model_dir):
    file_name = os.path.join(model_dir, 'hyper_params.txt')
    input_file = None
    with open(file_name, 'r') as f:
        args = {}
        for line in f.readlines():
            if '\t' in line:
                key, value = line.split('\t')
                if value.startswith('['): # list of hidden dimensions
                    f = lambda x: "".join(c for c in x if c not in ['\"', '\'', ' ', '\n', '[', ']']) 
                    l = [int(f(i)) for i in value.split(',')]
                    args[key.strip()] = l
                else:
                    args[key.strip()] = str_to_num(value.strip())
            else:
                input_file = line.strip()
    return args, input_file


def load_hdf_data(path, network_name='network', feature_name='features'):
    with h5py.File(path, 'r') as f:
        network = f[network_name][:]
        features = f[feature_name][:]
        node_names = f['gene_names'][:]
        train_mask = f['mask_train'][:]
        if 'feature_names' in f:
            feature_names = f['feature_names'][:]
        else:
            feature_names = None
        positives = []
        y_train = f['y_train'][:]
        positives.append(y_train.flatten())
        if 'y_test' in f:
            positives.append(f['y_test'][:].flatten())
        if 'y_val' in f:
            positives.append(f['y_val'][:].flatten())
        genes_pos = set()
        for group in positives:
            genes_pos.update(np.nonzero(group)[0])
        genes_pos = set(node_names[i,1] for i in genes_pos)
        if 'features_raw' in f:
            features_raw = f['features_raw'][:]
        else:
            features_raw = None
    return network, features, features_raw, y_train, train_mask, node_names, feature_names, genes_pos


def get_direct_neighbors(adj, node):
    neighbors = []
    for idx, val in enumerate(adj[node,:]):
        if math.isclose(val, 1):
            neighbors.append(idx)
    return neighbors


def get_top_neighbors(idx_gene, adj, attr_mean, attr_std):
    edge_list = []
    nodes_attr = {}
    sources = [idx_gene]
    for support in range(2, len(attr_mean)):
        for source in sources:
            next_neighbors = get_direct_neighbors(adj, source)
            for next_node in next_neighbors:
                if not (next_node, source) in edge_list:
                    edge_list.append((source, next_node))
                    if not next_node in nodes_attr:
                        val_mean = (attr_mean[support][idx_gene, next_node] + attr_mean[support][next_node, idx_gene])/2
                        val_std = (attr_std[support][idx_gene, next_node] + attr_std[support][next_node, idx_gene])/2
                        nodes_attr[next_node] = (val_mean, val_std)
        sources = next_neighbors
    return edge_list, nodes_attr


def save_edge_list(edge_list, nodes_attr, gene, node_names, out_dir):
    with open("{}{}.edgelist".format(out_dir, gene), "wt") as out_handle:
        out_handle.write("SOURCE\tTARGET\tLRP_ATTR_TARGET\tLABEL_TARGET\n")
        for edge in edge_list:
            out_handle.write("{}\t{}\t{}\t{}\n".format(*edge, nodes_attr[edge[1]][0], node_names[edge[1]]))


def _hide_top_right(ax):
    ax.spines['right'].set_visible(False)
    ax.spines['top'].set_visible(False)
    ax.yaxis.set_ticks_position('left')
    ax.xaxis.set_ticks_position('bottom')


def save_plots(feature_names, idx_gene, features, feat_attr_mean, feat_attr_std, node_names, genes_pos, most_important, least_important, out_dir):
    fig, ax = plt.subplots(nrows = 3, ncols = 1, figsize = (12, 6))
    # original feature plot
    x = np.arange(len(feature_names))
    ax[0].set_title(node_names[idx_gene])
    ax[0].bar(x, features[idx_gene,:].tolist()[0], color="#67a9cf")
    ax[0].set_xticks(x)
    ax[0].set_xticklabels(feature_names)
    ax[0].set_ylabel("feature value")
    # LRP attributions for each feature
    ax[1].bar(x, feat_attr_mean[idx_gene,:], color="#5ab4ac", yerr=feat_attr_std[idx_gene,:])
    ax[1].set_xticklabels(feature_names)
    ax[1].set_xticks(x)
    ax[1].set_ylabel("LRP attribution")
    for i, val in enumerate(feat_attr_mean[idx_gene,:]):
        if val < 0:
            ax[1].patches[i].set_facecolor("#d8b365")
    # most/least important neighbors
    neighbors = most_important + least_important[::-1]
    x = np.arange(len(neighbors))
    ax[2].bar(x, [i[1][0] for i in neighbors], color="#5ab4ac", yerr= [i[1][1] for i in neighbors])
    ax[2].set_xticks(x)
    ax[2].set_xticklabels([i[0] for i in neighbors])
    ax[2].set_ylabel("LRP attribution")
    for i, val in enumerate([i[1][0] for i in neighbors]):
        if val < 0:
            ax[2].patches[i].set_facecolor("#d8b365")
    for i, (gene, val) in enumerate(neighbors):
        if gene in genes_pos:
            ax[2].get_xticklabels()[i].set_color("red")
    # finalize
    _hide_top_right(ax[0])
    _hide_top_right(ax[1])
    _hide_top_right(ax[2])
    for axis in ax:
        for tick in axis.get_xticklabels():
            tick.set_rotation(90)
    plt.tight_layout()
    fig.savefig("{}{}.pdf".format(out_dir, node_names[idx_gene]))
    fig.clf()
    plt.close('all')


def plot_violins(matrix, out_dir, file_name):
    fig, ax = plt.subplots(nrows = 1, ncols = 1, figsize = (15, 5))
    _hide_top_right(ax)
    ax.violinplot(matrix.T.tolist())
    plt.tight_layout()
    fig.savefig(out_dir + file_name)
    fig.clf()
    plt.close('all')

    
def save_average_plots(attr_mean, attr_std, idx_gene, adj, node_names,
                       out_dir, features, genes_pos, feature_names):
    edge_list, nodes_attr = get_top_neighbors(idx_gene, adj, attr_mean, attr_std)
    save_edge_list(edge_list, nodes_attr, node_names[idx_gene], node_names, out_dir)
    nodes_sorted = sorted(nodes_attr.items(), key=lambda x: x[1][0])
    nodes_sorted = [(node_names[idx], attr) for idx, attr in nodes_sorted]
    most_important = nodes_sorted[-30:][::-1]
    least_important = nodes_sorted[:15]
    f_names = feature_names if not feature_names is None else np.arange(features.shape[1])
    save_plots(f_names, idx_gene, features, attr_mean[0], attr_std[0],
               node_names, genes_pos, most_important, least_important, out_dir)


def get_attributions(de, model, idx_gene, placeholders, features, support):
    mask_gene = np.zeros((features.shape[0],1))
    mask_gene[idx_gene] = 1
    return de.explain(method="elrp",
                      T=tf.nn.sigmoid(model.outputs) * mask_gene,
                      X=[placeholders['features'], *placeholders["support"]],
                      xs=[features, *support])
    

def interpretation(model_dirs, gene, out_dir, adj, features, y_train, support,
                   node_names, feature_names, genes_pos, num_supports, args, raw_features):
    attributions = [[] for _ in range(num_supports+1)]
    print("Now: {}".format(gene))
    for model_dir in model_dirs:
        ckpt = tf.train.get_checkpoint_state(checkpoint_dir=model_dir)
        placeholders = {
            'support': [tf.placeholder(tf.float32) for _ in range(num_supports)],
            'features': tf.placeholder(tf.float32, shape=features.shape),
            'labels': tf.placeholder(tf.float32, shape=(None, y_train.shape[1])),
            'labels_mask': tf.placeholder(tf.int32),
            'dropout': tf.placeholder_with_default(0., shape=()),
            'num_features_nonzero': tf.placeholder(tf.int32)
        }
        os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
        with tf.Session() as sess:
            with DeepExplain(session=sess) as de:
                model = MYGCN(placeholders=placeholders,
                              input_dim=features.shape[1],
                              learning_rate=args['lr'],
                              weight_decay=args['decay'],
                              num_hidden_layers=len(args['hidden_dims']),
                              hidden_dims=args['hidden_dims'],
                              pos_loss_multiplier=args['loss_mul'],
                              logging=False, sparse_network=False)
                model.load(ckpt.model_checkpoint_path, sess)
                try:
                    idx_gene = node_names.index(gene)
                except:
                    print("Warning: '{}' not found in label list".format(gene))
                    break
                new_attr = get_attributions(de, model, idx_gene, placeholders, features, support)
                assert len(attributions) == len(new_attr)
                for i in range(len(new_attr)):
                    attributions[i].append(new_attr[i])
        tf.reset_default_graph()
    if attributions[0] == []: return
    # create avg plots for this gene
    attributions = [np.array(attributions[i]) for i in range(len(attributions))]
    attr_mean = [np.mean(x, axis=0) for x in attributions]
    attr_std = [np.std(x, axis=0) for x in attributions]
    if not out_dir is None:
        save_average_plots(attr_mean, attr_std, idx_gene, adj, node_names,
                           out_dir, raw_features, genes_pos, feature_names)
    return attributions[0]


def interpretation_avg(model_dir, genes, out_dir):
    if not out_dir is None:
        if out_dir[-1] != "/":
            out_dir += "/"
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
    args, data_file = load_hyper_params(model_dir)
    print("Load: {}".format(data_file))

    data = load_hdf_data(data_file, feature_name='features')
    adj, features, raw_features, y_train, _, node_names, feature_names, genes_pos = data
    # get raw features from numpy file if they are not in container
    if raw_features is None:
        #raw_features = features
        raw_features = np.load('../data/pancancer/multiomics_features_raw_fc.npy')
    node_names = [x[1] for x in node_names]
    features = utils.preprocess_features(lil_matrix(raw_features), sparse=False)
    if args["support"] > 0:
        support = utils.chebyshev_polynomials(adj, args["support"], sparse=False)
        num_supports = 1 + args["support"]
    else:
        support = [np.eye(adj.shape[0])]
        num_supports = 1

    # get all subdirs in the model dir
    model_dirs = [os.path.join(model_dir, i) for i in os.listdir(model_dir) if i.startswith('cv_')]
    assert(np.all([os.path.isdir(i) for i in model_dirs])) # make sure those are dirs
    for path in model_dirs:
        if not os.path.isdir(path):
            raise RuntimeError("Path '{}' not found.".format(path))
    
    attributions_all = []
    for gene in genes:
        attr = interpretation(model_dirs, gene, out_dir, adj, features, y_train, support,
                              node_names, feature_names, genes_pos, num_supports, args,
                              np.matrix(raw_features))
        attributions_all.append(attr)
    return attributions_all


def main():
    parser = argparse.ArgumentParser(
    description='Do average LRP interpretation on a given cross-validated model')
    parser.add_argument('-m', '--modeldir',
                        help='Path to the trained model directory',
                        dest='model_dir',
                        required=True)
    parser.add_argument('-g', '--genes',
                        help='List of gene symbols for which to do interpretation',
                        nargs='+',
                        dest='genes',
                        default=None)
    args = parser.parse_args()

    # get some genes to do interpretation for
    if args.genes is None:
        genes = ["NCK1", "ITGAX", "PAG1", "SH2B2", "CEBPB", "CHD1", "CHD3", "CHD4",
                 "TP53", "PADI4", "RBL2", "BRCA1", "BRCA2", "NOTCH2", "NOTCH1",
                 "MYOC", "ZNF24", "SIM1", "HSP90AA1", "ARNT", "KRAS", "SMAD6", "SMAD4", 
                 "STAT1", "MGMT", "NCOR2", "RUNX1", "KAT7", "IDH1", "IDH2", "DROSHA",
                 "WRN", "FOXA1", "RAC1", "BIRC3", "DNM2", "MYC"]
    else:
        genes = args.genes
    
    # create the output dir (within first model dir)
    # at the end output dir contains the average lrp values over all provided models
    out_dir = os.path.join(args.model_dir, 'lrp_sigmoid')
    if not os.path.isdir(out_dir):
        os.mkdir(out_dir)
    interpretation_avg(model_dir=args.model_dir,
                       genes=genes,
                       out_dir=out_dir)

if __name__ == "__main__":
    main()