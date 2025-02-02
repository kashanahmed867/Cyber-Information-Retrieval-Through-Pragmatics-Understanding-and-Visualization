import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from sklearn.model_selection import train_test_split
import tensorflow as tf
import tensorflow_hub as hub
from keras import backend as K
from keras.models import Model, Input
from keras.layers.merge import add
from keras.layers import LSTM, Embedding, Dense, TimeDistributed, Dropout, Bidirectional, Lambda
from keras.models import load_model


os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

plt.style.use("ggplot")
data = pd.read_csv("../testdata/ner_dataset.csv", encoding="latin1")

data = data.drop(['POS'], axis =1)
data = data.fillna(method="ffill")

data.tail(12)
words = set(list(data['Word'].values))
words.add('PADword')
n_words = len(words)
n_words
#print(n_words)
tags = list(set(data["Tag"].values))
n_tags = len(tags)
n_tags
#print(n_tags)
#print(data)

# in charge of converting every sentence with its named entities (tags) into a list of tuples [(word, named entity), …]
class SentenceGetter(object):

    def __init__(self, data):
        self.n_sent = 1
        self.data = data
        self.empty = False
        agg_func = lambda s: [(w, t) for w, t in zip(s["Word"].values.tolist(), s["Tag"].values.tolist())]
        self.grouped = self.data.groupby("Sentence #").apply(agg_func)
        self.sentences = [s for s in self.grouped]

    def get_next(self):
        try:
            s = self.grouped["Sentence: {}".format(self.n_sent)]
            self.n_sent += 1
            return s
        except:
            return None


#sentence example
getter = SentenceGetter(data)
sent = getter.get_next()
#print(sent)

#sentences number
sentences = getter.sentences
#print(len(sentences))


largest_sen = max(len(sen) for sen in sentences)
print('biggest sentence has {} words'.format(largest_sen))


plt.hist([len(sen) for sen in sentences], bins= 50)
plt.show()

#In order to feed our sentences into a LSTM network, they all need to be the same size
#add padding words
max_len = 50
X = [[w[0]for w in s] for s in sentences]
new_X = []
for seq in X:
    new_seq = []
    for i in range(max_len):
        try:
            new_seq.append(seq[i])
        except:
            new_seq.append("PADword")
    new_X.append(new_seq)
new_X[15]


from keras.preprocessing.sequence import pad_sequences
tags2index = {t:i for i,t in enumerate(tags)}
y = [[tags2index[w[1]] for w in s] for s in sentences]
y = pad_sequences(maxlen=max_len, sequences=y, padding="post", value=tags2index["O"])
y[15]

#split data into training and testing
#load elmo embedding
X_tr, X_te, y_tr, y_te = train_test_split(new_X, y, test_size=0.1, random_state=2018)
sess = tf.compat.v1.Session()
K.set_session(sess)
elmo_model = hub.Module("https://tfhub.dev/google/elmo/2", trainable=True)
sess.run(tf.compat.v1.global_variables_initializer())
sess.run(tf.compat.v1.tables_initializer())

#convert sentences into elmo embedding
batch_size = 32
def ElmoEmbedding(x):
    return elmo_model(inputs={"tokens": tf.squeeze(tf.cast(x,    tf.string)),"sequence_len": tf.constant(batch_size*[max_len])
                     },
                      signature="tokens",
                      as_dict=True)["elmo"]


#build neural network
input_text = Input(shape=(max_len,), dtype=tf.string)
embedding = Lambda(ElmoEmbedding, output_shape=(max_len, 1024))(input_text)
x = Bidirectional(LSTM(units=512, return_sequences=True,
                       recurrent_dropout=0.2, dropout=0.2))(embedding)
x_rnn = Bidirectional(LSTM(units=512, return_sequences=True,
                           recurrent_dropout=0.2, dropout=0.2))(x)
x = add([x, x_rnn])  # residual connection to the first biLSTM
out = TimeDistributed(Dense(n_tags, activation="softmax"))(x)
model = Model(input_text, out)
model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["acc"])

X_tr, X_val = X_tr[:1213*batch_size], X_tr[-135*batch_size:]
y_tr, y_val = y_tr[:1213*batch_size], y_tr[-135*batch_size:]
y_tr = y_tr.reshape(y_tr.shape[0], y_tr.shape[1], 1)
y_val = y_val.reshape(y_val.shape[0], y_val.shape[1], 1)
history = model.fit(np.array(X_tr), y_tr, validation_data=(np.array(X_val), y_val),batch_size=batch_size, epochs=3, verbose=1)

# from seqeval.metrics import precision_score, recall_score, f1_score, classification_report
#
# X_te = X_te[:149 * batch_size]
# test_pred = model.predict(np.array(X_te), verbose=1)
#
# idx2tag = {i: w for w, i in tags2index.items()}
#
#
# def pred2label(pred):
#     out = []
#     for pred_i in pred:
#         out_i = []
#         for p in pred_i:
#             p_i = np.argmax(p)
#             out_i.append(idx2tag[p_i].replace("PADword", "O"))
#         out.append(out_i)
#     return out
#
# def test2label(pred):
#     out = []
#     for pred_i in pred:
#         out_i = []
#         for p in pred_i:
#             out_i.append(idx2tag[p].replace("PADword", "O"))
#         out.append(out_i)
#     return out
#
#
#
#
# pred_labels = pred2label(test_pred)
# test_labels = test2label(y_te[:149 * 32])
# print(classification_report(test_labels, pred_labels))
#
#
# i = 390
# p = model.predict(np.array(X_te[i:i+batch_size]))[0]
# p = np.argmax(p, axis=-1)
# print("{:15} {:5}: ({})".format("Word", "Pred", "True"))
# print("="*30)
# for w, true, pred in zip(X_te[i], y_te[i], p):
#     if w != "__PAD__":
#         print("{:15}:{:5} ({})".format(w, tags[pred], tags[true]))