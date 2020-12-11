from keras.models import Sequential
from keras.layers import Dense, Dropout, SpatialDropout1D, Conv1D, MaxPooling1D, Activation, Embedding, Flatten, GlobalMaxPooling1D, LSTM
from keras import regularizers, callbacks, optimizers
from keras.models import load_model
from keras.utils import plot_model
import argparse
import os
import logging
from data_loaders import TextsLoader, TokenizerLoader, WordVectorsLoader, TextSequencesLoader
import matplotlib.pyplot as plt
import numpy as np
from sklearn import metrics
import tensorflow as tf
import pandas as pd
import sys

from sklearn.model_selection import train_test_split


os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
conv_version = 5
lstm_version = 1
conv_lstm_version = 1

sem_eval_path = ''
seq_len =  800 # 5000 # 2500 # Inferred from checking the sequences length distributions
words_count = 1207#438
embedding_mode = 0
crowdsourced = False
algorithm = 0
final_model_name = ''

def load_embedding_layer(tokenizer):
    # Get vocabulary size
    vocab_size = len(tokenizer.word_index) + 1
    logging.info('Vocab size: {}'.format(vocab_size))
    logging.info("tokenizer word_index", tokenizer.word_index)

    # Load word vectors
    word_vectors_loader = WordVectorsLoader(sem_eval_path, crowdsourced, embedding_mode)
    word_vectors_loader.load()
    weights_matrix = word_vectors_loader.create_embedding_weights_matrix(tokenizer.word_index)
    
    return Embedding(input_dim=vocab_size, 
                                output_dim=weights_matrix.shape[1], 
                                weights=[weights_matrix],
                                input_length=seq_len,
                                trainable=False
                                )

def define_conv_lstm_model(tokenizer, units=128, filters=64, kernel_size=4): # farkl olarak senteces input'unu alıyor
    model = Sequential()

    embedding_layer = load_embedding_layer(tokenizer)
    model.add(embedding_layer)
    
    
    
    model.add(Conv1D(filters,
                    kernel_size,
                    activation='relu'))
    model.add(Dropout(0.3))
    model.add(MaxPooling1D(pool_size=4))

    model.add(Conv1D(filters,
                    kernel_size,
                    activation='relu'))
    model.add(Dropout(0.3))
    model.add(MaxPooling1D(pool_size=2))
    
    model.add(LSTM(units, dropout=0.2, recurrent_dropout=0.2))

    model.add(Dense(1, activation='sigmoid'))

    return model

def generate_new_model_name():
    alg = ''
    version = 1
    if algorithm == 0:
        alg = 'conv'
        version = 000
    elif algorithm == 1:
        alg = 'conv_lstm'
        version = 100  
    elif algorithm == 2:
        alg = 'lstm'
        version = 200
    else:
        raise Exception('Unknown algorithm')
    return 'words_{}_model_w{}_v{}'.format(alg, embedding_mode, version)

def load_pretrained(model, model_name, model_weights_location):
    model_file = os.path.join(sem_eval_path, 'models', "{}.h5".format(model_name))
    if os.path.isfile(model_file) and os.path.isfile(model_weights_location):
        model_file_time = os.path.getmtime(model_file)
        weights_file_time = os.path.getmtime(model_weights_location)
        if weights_file_time > model_file_time:
            logging.info('Loading the weights (latest modified).')
            model.load_weights(model_weights_location)
        else:
            model = load_model(model_file)
            logging.info('Loading the model (latest modified)')
    elif os.path.isfile(model_weights_location):
        model.load_weights(model_weights_location)
        logging.info('Loading the weights')
    elif os.path.isfile(model_file):
        model = load_model(model_file)
        logging.info('Loading the model')
    else:
        raise Exception("Neither model nor weights file exists")
    return model

def plot_model_history(history, model_name):
    plt.plot(history.history['acc'])
    plt.plot(history.history['loss'])
    plt.title('trainn accuracy and loss')
    plt.ylabel('accuracy')
    plt.xlabel('epoch')
    plt.savefig(os.path.join(sem_eval_path, 'models', '{}_history.png'.format(model_name)))

def evaluate_model(model, X_val, y_val):
    y_predict = (np.asarray(model.predict(X_val))).round()

    acc = metrics.accuracy_score(y_val, y_predict)
    logging.info('Accuracy: {}'.format(acc))
    print('Accuracy: {}'.format(acc))
    # let's see
    logging.info('y_val: {}'.format(y_val))
    logging.info('y_predict: {}'.format(y_predict))
    
    conf_matrix = metrics.confusion_matrix(y_val, y_predict)
    logging.info('Confusion matrix: {}'.format(conf_matrix))

    precision = metrics.precision_score(y_val, y_predict)
    logging.info('Precision score: {}'.format(precision))

    recall = metrics.recall_score(y_val, y_predict)
    logging.info('Recall score: {}'.format(recall))

    val_f1 = metrics.f1_score(y_val, y_predict)
    logging.info('F1 score: {}'.format(val_f1))

    model_plot_file = os.path.join(sem_eval_path, 'models', '{}.png'.format(final_model_name))
    plot_model(model, to_file=model_plot_file, show_shapes=True, show_layer_names=True)

def transferLearning(model):
    print("Transfer learning is on!")
    for l in model.layers[:-1]:
      l.trainable = False
    #model.add(Dense(1, activation='sigmoid'))
    return model
    
    
def main():         
    tf.compat.v1.Session(config=tf.compat.v1.ConfigProto(log_device_placement=True))
    parser = argparse.ArgumentParser()
    parser.add_argument("--path",'-p', default="/home/agon/Files/SemEval",
                        help="Use this argument to change the SemEval directory path (the default path is: '/home/ashwath/Files/SemEval')")
    parser.add_argument("--crowdsourced", '-c', action='store_true', default="False",
                        help="Use this argument to work with the crowdsourced file")
    parser.add_argument("--model", '-m', default="", #"words_conv_lstm_model_w1_v1"
                        help="Use this argument to continue training a stored model")
    parser.add_argument("--word_vectors", '-w', default="0",  # 2 for BERT
                        help="Use this argument to set the word vectors to use: 0: Google's Word2vec, 1: GloVe, 2: Fasttext, 3: Custom pretrained word2vec, 4: Custom pretrained Fasttext, 5: Custom pretrained news word2vec. Default: 0")
    parser.add_argument("--algorithm", '-a', default="0", # 1 used''!
                        help="Use this argument to set the algorithm to use: 0: CNN, 1: CNN + LSTM, 2: LSTM. Default: 0")
    parser.add_argument("--learning_rate", '-l', default="0.001",
                        help="Use this argument to set the learning rate to use. Default: 0.001")
    parser.add_argument("--evaluate", '-e', action='store_true', default="False", # True
                        help="Use this argument to set run on evaluation mode")
    args = parser.parse_args()
    
    global sem_eval_path
    sem_eval_path = args.path

    global embedding_mode
    embedding_mode = int(args.word_vectors)

    global algorithm
    algorithm = int(args.algorithm)

    evaluate_mode = args.evaluate

    global seq_len
    sentences = False
    if algorithm == 0:
        seq_len = 500 #700 #5000
    elif algorithm == 1:
        seq_len = 800 #2064
    elif algorithm == 2:
        seq_len = 100
        sentences = True
    else:
        raise Exception('Unknown algorithm')

    model_name = args.model
    model_dir = os.path.join(sem_eval_path, 'models')
    new_model_name = generate_new_model_name()
    model_location = os.path.join(model_dir, '11{}.h5'.format(new_model_name))
    model_weights_location = os.path.join(model_dir, '{}_weights.h5'.format(new_model_name))

    # ---LOGS---
    logs_path = os.path.join(sem_eval_path, 'logs', '{}_log.log'.format(model_name if model_name else new_model_name))
    logging.basicConfig(filename=logs_path, filemode='w', 
                    format='%(asctime)s : %(levelname)s : %(message)s', level=logging.INFO)
    logging.info('model_location: {}'.format(model_location))
    
    global crowdsourced
    crowdsourced = args.crowdsourced

    learning_rate = float(args.learning_rate)
    batch_size = 32 # default

    # Get data(OLD)
    texts_loader = TextsLoader(sem_eval_path, crowdsourced, logs_path)
    train_texts, y_train = texts_loader.load(sentences=sentences)
    logging.info('Train shape: {}'.format(train_texts.shape))
    logging.info('Number of biased samples: {}'.format(len(y_train[y_train == 1])))
    logging.info('Number of non-biased samples: {}'.format(len(y_train[y_train == 0])))
    
    # Get data(NEW)
    #new_df = pd.read_csv("predicted_200k.csv")
    #y_train = new_df['argmax']
    #train_texts = new_df['tweet']
    
    #new_df = pd.read_csv("formatted_allsides.csv")
    #y_train = new_df['predicted_hyperpartisan']
    #train_texts = new_df['content'] + new_df['title']
    
    # Get Tweets data
    '''
    df_ = pd.read_csv("84k_pol.csv", encoding= 'unicode_escape')
    df_['Tweet'] = df_['Tweet'].astype('str')
    df_t = df_[(~df_.Tweet.fillna('').str.isnumeric())]
    
    X = df_t['Tweet']
    Y = df_t['Party']
    '''
    df_tweets = pd.read_csv("data_to_classify.csv", encoding= 'unicode_escape')
    df_tweets['Tweet'] = df_tweets['Tweet'].astype('str')
    
    
    df_tweets['Partisan'] = df_tweets['Partisan'].replace({'Democrat' : 1, 'Republican' : 0})
    
    X = df_tweets['Tweet']
    Y = df_tweets['Partisan']
    
    train_texts_tl, X_val, y_train_tl, y_val = train_test_split( X, Y, test_size=0.33, random_state=42)
    print("X Val:", X_val.shape)
    print("Y Val:", y_val.shape)
    
    #logging.info('Train shape: {}'.format(train_texts.shape))
    #logging.info('Number of biased samples: {}'.format(len(y_train[y_train == 1])))
    #logging.info('Number of non-biased samples: {}'.format(len(y_train[y_train == 0])))
    '''
    val_texts, y_val = texts_loader.load(sentences=sentences, validation=True)
    logging.info('Validation shape: {}'.format(val_texts.shape))
    logging.info('Number of biased samples (burası çokomelli!!! maine texts_loader.load(sentences[] ile çağrılıyor: {}'.format(len(y_val[y_val == 1])))
    logging.info('Number of non-biased samples: {}'.format(len(y_val[y_val == 0])))
    logging.info(train_texts[:20])
    logging.info('-----------------------------------------------------------------------------------------------------')
    '''
    tokenizer = TokenizerLoader(train_texts, sem_eval_path, logs_path, most_common_count=words_count).load()

    sequences_loader = TextSequencesLoader(tokenizer, seq_len, sem_eval_path=sem_eval_path)
    X_train = sequences_loader.load(train_texts, truncate_sequences=(algorithm == 2))
    X_train_tl = sequences_loader.load(train_texts_tl, truncate_sequences=(algorithm == 2))
    
    zeroes = []
    for seq in X_train:
        seq_zeroes = 0
        for item in seq:
            if item == 0:
                seq_zeroes += 1
        zeroes.append(seq_zeroes)
    zeroes = np.array(zeroes)
    logging.info('Min. number of zeroes: {}'.format(zeroes.min()))
    logging.info('Avg. number of zeroes: {}'.format(zeroes.mean()))
    logging.info('Std. number of zeroes: {}'.format(zeroes.std()))
    logging.info('Max. number of zeroes: {}'.format(zeroes.max()))
    logging.info('Training sequences: ')
    logging.info(X_train[:20])
    logging.info('-----------------------------------------------------------------------------------------------------')
    '''
    if len(sequences_loader.indices_to_remove) > 0:
        logging.info('Removing train {} sequences'.format(len(sequences_loader.indices_to_remove)))
        logging.info('X_train pre shape: {}'.format(X_train.shape))
        X_train = np.delete(X_train, sequences_loader.indices_to_remove, axis=0)
        logging.info('X_train post shape: {}'.format(X_train.shape))
        logging.info('y_train pre shape: {}'.format(y_train.shape))
        y_train.drop(y_train.index[sequences_loader.indices_to_remove], inplace=True)
        logging.info('y_train post shape: {}'.format(y_train.shape))
    '''
    '''
    # sequences_loader.indices_to_remove
    #X_val = sequences_loader.load(val_texts)
    #if len(sequences_loader.indices_to_remove) > 0:
    #    logging.info('Removing validation {} sequences'.format(len(sequences_loader.indices_to_remove)))
    #    logging.info('X_val pre shape: {}'.format(X_val.shape))
    #    X_val = np.delete(X_val, sequences_loader.indices_to_remove, axis=0)
    #    logging.info('X_val post shape: {}'.format(X_val.shape))
    #    logging.info('y_val pre shape: {}'.format(y_val.shape))
    #    y_val.drop(y_val.index[sequences_loader.indices_to_remove], inplace=True)
    #    logging.info('y_val post shape: {}'.format(y_val.shape))
    '''
    seq_len = sequences_loader.seq_len

    if algorithm == 0:
        model = define_conv_model(tokenizer)
    elif algorithm == 1:
        model = define_conv_lstm_model(tokenizer)
    elif algorithm == 2:
        model = define_lstm_model(tokenizer)
    else:
        raise Exception('Unknown algorithm')
        
    if model_name:
        model = load_pretrained(model, model_name, model_weights_location)

    global final_model_name
    final_model_name = model_name if model_name else new_model_name
    
    logging.info(model.summary())

    if evaluate_mode is True:                                   # MAKE EVALUATE MODE ON
        evaluate_model(model, X_val, y_val)
    else:
        # Implement Early Stopping
        early_stopping_callback = callbacks.EarlyStopping(monitor='val_loss',#val_loss yerine -> loss
                                min_delta=0,
                                patience=5,
                                verbose=1)
                                #   restore_best_weights=True)
        save_best_model = callbacks.ModelCheckpoint(model_weights_location, monitor='val_loss', verbose=1, save_best_only=True, mode='auto')#val_loss yerine -> loss
        
        adam = optimizers.Adam(lr=learning_rate)
        '''
        model.compile(loss='binary_crossentropy',
                        optimizer=adam,
                        metrics=['accuracy'])
                        
        # validation_data=(X_val, y_val), silindi
        history = model.fit(X_train, y_train,
                    batch_size=batch_size,
                    epochs=5,
                    verbose=2,
                    callbacks=[early_stopping_callback, save_best_model])
        
        
        #model.load_weights(model_weights_location)
                    
        model = transferLearning(model)
        '''
        model.compile(loss='binary_crossentropy',
                        optimizer=adam,
                        metrics=['accuracy'])
        
        
        history = model.fit(X_train_tl, np.array(y_train_tl),
                    batch_size=batch_size,
                    epochs=10,
                    verbose=2,
                    callbacks=[early_stopping_callback])
                    
        print("done!")
        #plot_model_history(history, final_model_name)

        logging.info('Model trained. Storing model on disk.')
        model.save(os.path.join(sem_eval_path, 'models_new'))
        logging.info('Model stored on disk.')

    
if __name__ == "__main__":
    main()