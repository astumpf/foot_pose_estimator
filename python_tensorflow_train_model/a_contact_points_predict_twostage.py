#!/usr/bin/env python
import math
import os
import scipy.io
import sys
import time

from utils import myPlots
import numpy as np
import tensorflow as tf
from tensorflow.python.framework import graph_util

from utils import myDataLoader as myLoader

#############################################
#
#   This script uses tensorflow to train a model to
#   make a prediction of multiple contact points of a foot pose (of a non-convex foot shape),
#   given the uneven terrain.
#
#   The training works in two stages:
#
#   Stage 1:
#   Learn to predict the edge points of a convex hull of the terrain under the fixed foot shape.
#   At the end of stage 1 the weights of the neural network of this stage are learned.
#
#   Stage 2:
#   Given the edge points of the convex hull under the fixed foot shape, predict the outer contact points.
#   The weights of stage 2 will be learned, and the weights of stage 1 can continue to change, they are not fixed.
#
#   The learned weights of the full network are stored ("frozen") in a model
#   which can be used later to make predictions.

############################################# CONFIG

nRuns = 5000
trainTestSplit = 66 # percent

fileName = 'training_data/a_stages_cnn_10_10/data_stages_cnn_10_10.mat'
matName = 'data'

clsIdx = 100
dataWidth = 10
dataHeight = 10
dataLen = dataWidth*dataHeight
batchSize = 50
clsIdxs = [100,200]

############################################# Directories for models, logging, etc

script_name = os.path.basename(sys.argv[0]).replace(".py", "")

def myMakeDir(path):
    if not os.path.exists(path):
        os.makedirs(path)

timeStr = time.strftime('%m_%d_%H_%M')  # easy to sort by filename
path = "generated_models/a_stages_cnn_10_10_"+script_name
myMakeDir(path)
path = path +"/a_stages_cnn_10_10_"+timeStr+".ckpt"
logPath = "training_logs/a_stages_cnn_10_10_"+script_name+"/logs_mycnn_"+timeStr
myMakeDir(logPath)

############################################# LOAD DATA
mat = scipy.io.loadmat(fileName)
data = mat[matName]

train, test = myLoader.splitData(data, trainTestSplit)



[train_terrain, train_edgePts, train_ctPts] = myLoader.split_by_idxs(train, clsIdxs)
[test_terrain, test_edgePts, test_ctPts] = myLoader.split_by_idxs(test, clsIdxs)

# reshape data
train_terrain = train_terrain.reshape(-1, 100)
test_terrain = test_terrain.reshape(-1, 100)
train_edgePts = train_edgePts.reshape(-1, 100)
test_edgePts = test_edgePts.reshape(-1, 100)
train_ctPts = train_ctPts.reshape(-1, 100)
test_ctPts = test_ctPts.reshape(-1, 100)

# contact points turn float values to 1's and 0's
train_ctPts_ones = np.copy(train_ctPts)
test_ctPts_ones = np.copy(test_ctPts)
train_ctPts_ones[train_ctPts_ones>0]=1
test_ctPts_ones[test_ctPts_ones>0]=1

# hull edge points turn float values to 1's and 0's
train_edgePts_ones = np.copy(train_edgePts)
test_edgePts_ones = np.copy(test_edgePts)
train_edgePts_ones[train_edgePts_ones>0]=1
test_edgePts_ones[test_edgePts_ones>0]=1

# fix zmp in the middle
middleWidth = math.floor(dataWidth/2)
middleHeight = math.floor(dataHeight/2)
test_zmp = [middleWidth,middleHeight]
train_zmp = [middleWidth,middleHeight]

train_x = train_terrain
test_x = test_terrain

############################################# HELPER FUNCTIONS

def weight_variable(shape, weightName):
  initial = tf.truncated_normal(shape, stddev=0.1, name=weightName)
  return tf.Variable(initial)

def bias_variable(shape, weightName):
  initial = tf.constant(0.1, shape=shape, name=weightName)
  return tf.Variable(initial)

############################################# DEFINE COMPUTATION GRAPH
########## STAGE 1: Convex hull edge points
# train this stage first without the second stage

# Input X
# [bathSizeUnspecified, height, width, channels(e.g. rgb)]
X = tf.placeholder("float", [None, 100], name="X")

# Ground truth place holder
YReal_edgePts = tf.placeholder("float", [None, 100])

# densely connected layer:
# From X predict YPred_edgePts
featVec = tf.reshape(X, [-1, 100])
W_dense1 = weight_variable([10 * 10, 10 * 10], weightName='wdense1')
featMap4 = tf.matmul(featVec, W_dense1)
featMap4 = tf.nn.relu(featMap4)
# densely connected layer
W_dense2 = weight_variable([10 * 10, 10 * 10], weightName='wdense2')
featMap5 = tf.matmul(featMap4, W_dense2)
featMap5 = tf.nn.relu(featMap5)
# densely connected layer
W_dense3 = weight_variable([10 * 10, 10 * 10], weightName='wdense3')
featMap6 = tf.matmul(featMap5, W_dense3)
featMap6 = tf.nn.relu(featMap6)
# densely connected layer
W_dense4 = weight_variable([10 * 10, 10 * 10], weightName='wdense4')
featMap7 = tf.matmul(featMap6, W_dense4)
featMap7 = tf.nn.relu(featMap7)

YPred_edgePts = featMap7

#############################################
########## STAGE 2: Use edge points to predict Contact points
# after stage 1 was trained, train the whole network including stage 2
# then the weights W_dense 1-7 contain pre trained parameters

# Ground truth contact pts
YReal_ctPts = tf.placeholder("float", [None, 100])

ZMP = tf.placeholder("float", [None, 100])

EdgePtsAndZMP = tf.concat(1, [YPred_edgePts, X])


W_dense5 = weight_variable([10 * 10 * 2, 10 * 10], weightName='wdense5')
#B1 = bias_variable([10 * 10])
featMap8 = tf.matmul(EdgePtsAndZMP, W_dense5) #+ B1
featMap8 = tf.nn.sigmoid(featMap8)

#featMap8 = tf.concat(1, [featMap8, ZMP])
W_dense6 = weight_variable([10 * 10, 10 * 10 * 2], weightName='wdense6')
#B2 = bias_variable([10 * 10])
featMap9 = tf.matmul(featMap8, W_dense6) #+ B2
featMap9 = tf.nn.sigmoid(featMap9)

W_dense7 = weight_variable([10 * 10  *2, 10 * 10 * 2], weightName='wdense7')
#B3 = bias_variable([10 * 10])
featMap10 = tf.matmul(featMap9, W_dense7) #+ B3
featMap10 = tf.nn.sigmoid(featMap10)

W_dense8 = weight_variable([10 * 10 * 2, 10 * 10], weightName='wdense8')
#B4 = bias_variable([10 * 10])
featMap11 = tf.matmul(featMap10, W_dense8) #+ B4
featMap11 = tf.nn.sigmoid(featMap11)

YPred_ctPts = featMap11
res = tf.identity(YPred_ctPts, name="myypred")


############################################# COST FUNCTION and OPTIMIZER

with tf.name_scope('costEdgePts'):
    cost_edgePts = tf.reduce_sum(tf.pow(YPred_edgePts - YReal_edgePts, 2))  # minimize squared error btw pred and ground truth
    tf.scalar_summary('costEdgePts', cost_edgePts)
    train_op_edgePts = tf.train.AdamOptimizer(learning_rate=0.0001).minimize(cost_edgePts, var_list=[W_dense1, W_dense2, W_dense3, W_dense4])

with tf.name_scope('costCtPts'):
    cost_ctPts = tf.reduce_sum(tf.pow(YPred_ctPts - YReal_ctPts, 2))  # minimize squared error btw pred and ground truth
    tf.scalar_summary('costCtPts', cost_ctPts)
    train_op_ctPts = tf.train.AdamOptimizer(learning_rate=0.001).minimize(cost_ctPts, var_list=[W_dense5, W_dense6, W_dense7, W_dense8])

############################################# SAVE AND STORE MODEL STUFF

# Add ops to save and restore all the variables.
init_op = tf.initialize_all_variables()
# Add ops to save and restore all the variables.
saver = tf.train.Saver()
restoredFlag = 0  # always starts with 0

def restoreModel(path):
    # Restore variables from disk.
    saver.restore(sess, path)
    print("Model restored.")
    return 1

def saveModel(path):
    save_path = saver.save(sess, path)
    print("Model saved in file: %s" % save_path)


# All plots use the test set
def plotPredictions_ctPts(nonBlocking):
        pred_ctPts = sess.run(YPred_ctPts, feed_dict={X: test_x, YReal_edgePts: test_edgePts}) # only for other_plots during training
        myPlots.plotShapes(test_edgePts, test_ctPts_ones, pred_ctPts, test_zmp, nonBlocking)

def plotPredictions_edgePts(nonBlocking):
    preds = sess.run(YPred_edgePts, feed_dict={X: test_x}) # dont need the second one here... , YReal_edgePts: test_edgePts
    myPlots.plotShapes(test_x, test_edgePts, preds, test_zmp, nonBlocking)

def plotPredictions_FULL_STAGES(nonBlocking):
    pred_edgePts = sess.run(YPred_edgePts, feed_dict={X: test_x})
    pred_ctPts = sess.run(YPred_ctPts,
                          feed_dict={X: test_x, YReal_edgePts: pred_edgePts})
    myPlots.plotShapes(test_edgePts, test_ctPts_ones, pred_ctPts, test_zmp, nonBlocking)


############################################# TRAIN & EVAL
def train(sess):

    # Launch the graph in a session
    # with tf.Session() as sess:
    print("Training edge points..")

    # Merge all the summaries and write them out to logs (by default)
    merged = tf.merge_all_summaries()
    train_writer = tf.train.SummaryWriter(logPath, sess.graph)

    # you need to initialize all variables
    sess.run(init_op)

    ############################################# Stage 1
    ##### Learn edge points of the convex hull of the terrain

    episodes1 = 1000
    bs = 128  # 64 faster convergence than 128 (lr 0.001) 32 even better with lr 0.0001
    for i in range(episodes1):

        for start, end in zip(range(0, len(train_x), bs), range(bs, len(train_x), bs)):
            sess.run(train_op_edgePts, feed_dict={X: train_x[start:end], YReal_edgePts: train_edgePts[start:end]})
        if np.mod(i, 100) == 0:
            print(i, sess.run(cost_edgePts, feed_dict={X: test_x, YReal_edgePts: test_edgePts}))
            plotPredictions_edgePts(nonBlocking=1)
            saveModel(path)
    print(i, sess.run(cost_edgePts, feed_dict={X: test_x, YReal_edgePts: test_edgePts}))

    plotPredictions_edgePts(nonBlocking=1)

    ############################################# Stage 2
    ##### Learn contact points based on the edge points
    print("Training contact points..")

    episodes2 = 5000
    bs = 32 # 1000 was great!  # 64 lr 0.0001 8300-8400 ; 32 0.0001 about the same; bs 128 lr 0.0001 7900s; bs 200 lr 0.0001 7900
    for i in range(episodes2):

        for start, end in zip(range(0, len(train_x), bs), range(bs, len(train_x), bs)):
            sess.run(train_op_ctPts, feed_dict={X: train_x[start:end], YReal_edgePts: train_edgePts[start:end], YReal_ctPts: train_ctPts_ones[start:end]})
        if np.mod(i, 50) == 0:
            print(i, sess.run(cost_edgePts, feed_dict={X: test_x, YReal_edgePts: test_edgePts}), sess.run(cost_ctPts, feed_dict={X: test_x, YReal_edgePts: test_edgePts, YReal_ctPts: test_ctPts_ones}))
            plotPredictions_ctPts(nonBlocking=1)
            saveModel(path)
    print(i, sess.run(cost_edgePts, feed_dict={X: test_x, YReal_edgePts: test_edgePts}), sess.run(cost_ctPts,
                                                                                                  feed_dict={X: test_x,
                                                                                                             YReal_edgePts: test_edgePts,
                                                                                                             YReal_ctPts: test_ctPts_ones}))
    saveModel(path)

    plotPredictions_ctPts(nonBlocking=0)

#####################
# end of training
#####################



def restore_and_pred():
    fileName = 'generated_models/a_stages_cnn_10_10_a_cnn_stages_10_10/a_stages_cnn_10_10_01_31_09_47.ckpt'
    restoreModel(fileName)
    '''
    plotPredictions_edgePts(nonBlocking=0)
    plotPredictions_edgePts(nonBlocking=0)
    plotPredictions_ctPts(nonBlocking=0)
    plotPredictions_ctPts(nonBlocking=0)
    plotPredictions_ctPts(nonBlocking=0)
    plotPredictions_ctPts(nonBlocking=0)
    plotPredictions_ctPts(nonBlocking=0)
    plotPredictions_ctPts(nonBlocking=0)
    '''
    plotPredictions_FULL_STAGES(nonBlocking=0)
    plotPredictions_FULL_STAGES(nonBlocking=0)
    plotPredictions_FULL_STAGES(nonBlocking=0)
    plotPredictions_FULL_STAGES(nonBlocking=0)


def freeze_model():
    # save all parameters that are necessary to make a prediction
    graph = tf.get_default_graph()
    input_graph_def = graph.as_graph_def()
    # graph = sess.graph
    # input_graph_def = sess.graph_def
    output_node_names = "myypred"
    # We use a built-in TF helper to export variables to constants
    output_graph_def = graph_util.convert_variables_to_constants(
        sess,  # The session is used to retrieve the weights
        input_graph_def,  # The graph_def is used to retrieve the nodes
        output_node_names.split(",")  # The output node names are used to select the usefull nodes
    )
    # Finally we serialize and dump the output graph to the filesystem
    with tf.gfile.GFile("frozen_model_stages_10_10_"+timeStr+".pb", "wb") as f:
        f.write(output_graph_def.SerializeToString())
    print 'saved and frozen'

#####################
# RUN !
#####################

with tf.Session() as sess:
    #train(sess)
    restore_and_pred()
    freeze_model()



