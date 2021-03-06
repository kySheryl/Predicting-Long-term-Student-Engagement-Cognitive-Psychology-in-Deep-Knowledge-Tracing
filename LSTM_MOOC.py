import pandas as pd
import numpy as np
# load dataset
df = pd.read_csv('/content/Self-regulated-spacing-online-class/processed data/SummarySpacingTime.csv')
# data preprocessing
df['crammer'] = np.where(df['crammers']=='Non-Crammer', 0, 1)

df = df.drop(columns=['examGrade', 'crammers'])

df = df.fillna(value = {'pretestGrade':df['pretestGrade'].mean(), "meanSessionDiff":df["meanSessionDiff"].mean()})

df['number of sessions' ]= df['nsessions']

FEATURES = ['meantimeToQuiz', 'npages','nactivities','timeInModule',
            'endToQuiz','meanSessionDiff', 'quizGrade','pretestGrade',
            'Nwords','Nactivities','Npages', 'nsessions']

df['nsessions_normal'] = df['nsessions']

USER_FEATURES = ['meantimeToQuiz',
                'npages','nactivities','timeInModule',
            'endToQuiz','meanSessionDiff', 'quizGrade','pretestGrade',
            'nsessions']

MODULE_FEATURES = ['Nwords','Nactivities','Npages']

MEAN_ALL = df.mean()
STD_ALL = df.std()
for col in ['meantimeToQuiz', 'npages','nactivities','timeInModule',
            'endToQuiz','meanSessionDiff', 'pretestGrade',
            'Nwords','Nactivities','Npages','ndays','quizGrade']:
  df[col] = (df[col] - MEAN_ALL[col]).div(STD_ALL[col])

df['nsessions_normal'] = np.log1p(df['nsessions_normal'])
df['nsessions'] = np.log1p(df['nsessions'])

# LSTM model
import tensorflow as tf
import keras
import tensorflow.keras.layers as L
import random
from random import choice
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.callbacks import ModelCheckpoint
from keras.models import load_model

tf.config.run_functions_eagerly(True)
random.seed(42)
tf.keras.backend.set_floatx('float64')

def train_model(X_train, X_test, M_train, M_test, y_train, y_test,n):
  user_input = keras.Input(shape = (n-1,9), name = 'user_input')
  module_input = keras.Input(shape = (n,14), name = 'module_input')
  user_to_lstm1 = L.Dense(64,
                          input_shape = (None, 9),
                          activation = 'relu')
  module_to_lstm1 =  L.Dense(64,
                          input_shape = (None, 14),
                          activation = 'relu')
  user_lstm = L.LSTM(256, input_shape = (None, 64))
  module_lstm = L.LSTM(256, input_shape = (None, 64))
  lstm_to_dense1 =  L.Dense(265,
                          input_shape = (None, 512),
                          activation = 'relu')
  dropout_1 = L.Dropout(0.1)
  dense1_to_dense2 =  L.Dense(128,
                          input_shape = (None, 256),
                          activation = 'relu')
  dense2_to_dense3 =  L.Dense(64,
                          input_shape = (None, 128),
                          activation = 'relu')
  dropout_3 = L.Dropout(0.1)
  dense3_to_dense4 =  L.Dense(32,
                          input_shape = (None, 64),
                          activation = 'relu')
  dense4_to_pred =  L.Dense(1,
                          input_shape = (None, 32),
                          activation = 'linear')

  user_lstm_input = user_to_lstm1(user_input)
  module_lstm_input = module_to_lstm1(module_input)

  user_lstm_output = user_lstm(user_lstm_input)
  module_lstm_output = module_lstm(module_lstm_input)

  # summation of lstm layers outputs
  lstm_output = tf.add(user_lstm_output, module_lstm_output)

  # feed forward neural network
  dense1 = lstm_to_dense1(lstm_output)
  dense2 = dense1_to_dense2(dropout_1(dense1))
  dense3 = dense2_to_dense3(dense2)
  dense4 = dense3_to_dense4(dropout_3(dense3))
  pred = dense4_to_pred(dense4)

  model = keras.Model(
      inputs=[user_input, module_input],
      outputs=[pred],
      name='lstm_model',
  )
  opt_adam = Adam(learning_rate = 0.0001)

  model.compile(
      optimizer=opt_adam,
      loss=  'mse',
      metrics = ['mse', 'mae']
  )

  # we choose the model with best validation loss
  mc = ModelCheckpoint('models/best_model_for_' + str(n) + '.h5', monitor='val_mse', mode='min', verbose=0)
  # early stopping to prevent overfit
  es = EarlyStopping(monitor='val_loss', mode='min', verbose=1, patience=40)

  history = model.fit(
    [X_train, M_train],
    y_train,
    batch_size = 64,
    epochs = 200,
    validation_data=([X_test, M_test], y_test),
    callbacks=[es, mc],
    verbose = 0
  )

  while True:
    try:
      model = load_model('models/best_model_for_' + str(n) + '.h5')
      break
    except FileNotFoundError:
      continue

  return model, history

users = df['ds_anon_user_id'].unique()

from sklearn.preprocessing import OneHotEncoder
module_encoder = OneHotEncoder(categories = [[1,2,3,4,5,6,7,8,9,10,11]])

def process_data(n):
    user_data = []
    module_data = []
    y = []

    for user in users:
      user_df = df[df['ds_anon_user_id'] == user]
      if len(user_df)>=n:
        # Objective: prediction the nsessions on n_th module
        
        # Get module features for first n_th modules
        user_df = user_df.head(n)
        encoded_module = module_encoder.fit_transform(user_df['module'].values.reshape(-1,1)).toarray()
        modules = user_df[MODULE_FEATURES].values

        # our target
        sessions = user_df['nsessions_normal'].values[-1] 
        
        # Get user features for first (n-1) modules
        # ['meantimeToQuiz', 'npages','nactivities','timeInModule',
        #   'endToQuiz','meanSessionDiff', 'quizGrade','pretestGrade',
        #   'nsessions']
        user_df = user_df.head(n-1)
        user = user_df[USER_FEATURES].values

        user_data.append(user)
        module_data.append(np.concatenate((modules, encoded_module), axis = 1))
        y.append([sessions])
      
    return np.array(user_data), np.array(module_data), np.array(y)

device_name = tf.test.gpu_device_name()
if device_name != '/device:GPU:0':
  raise SystemError('GPU device not found')
print('Found GPU at: {}'.format(device_name))

import math
from sklearn.model_selection import train_test_split
for n in [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]:
  user_data, module_data, y = process_data(n)
  print(y.std())
  X_train, X_test, M_train, M_test, y_train, y_test = train_test_split(user_data, module_data, y, test_size=0.1, random_state=22)
  X_train, X_val, M_train, M_val, y_train, y_val = train_test_split(X_train, M_train, y_train, test_size=int(0.1*len(user_data)), random_state=106)
  
  model, history = train_model(X_train, X_val, M_train, M_val, y_train, y_val, n)
  metrics = model.evaluate([X_test, M_test], y_test, return_dict = False)
  metrics_train = model.evaluate([X_train, M_train], y_train, return_dict = False)

  loss_his = history.history
  mse = min(loss_his['val_mse'])

  print("The metric for ", n, " are: ") 
  print("TRAIN_RMSE: %.3f " % (math.sqrt(metrics_train[1])))
  print("VAL_RMSE: %.3f " % (math.sqrt(mse)))
  print("TEST_RMSE: %.3f " % (math.sqrt(metrics[1])))

