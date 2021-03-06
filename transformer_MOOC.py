# Prepare Dataset
import pandas as pd
import numpy as np

# load dataset
df = pd.read_csv('/content/Self-regulated-spacing-online-class/processed data/SummarySpacingTime.csv')

# data preprocess
df['crammer'] = np.where(df['crammers']=='Non-Crammer', 0, 1)

df = df.drop(columns=['examGrade', 'crammers'])

df = df.fillna(value = {'pretestGrade':df['pretestGrade'].mean(), "meanSessionDiff":df["meanSessionDiff"].mean()})

MEAN_ALL = df.mean()
STD_ALL = df.std()
for col in ['meantimeToQuiz', 'npages','nactivities','timeInModule',
            'endToQuiz','meanSessionDiff', 'pretestGrade',
            'Nwords','Nactivities','Npages','ndays','quizGrade']:
  df[col] = (df[col] - MEAN_ALL[col]).div(STD_ALL[col])

df['nsessions'] = np.log1p(df['nsessions'])

# set the n value
n = 3
DROPOUT = 0.1

"""# Transformer"""

# we don't consider the users whose number of completed module in less than (n+1)
valid_user = []

for user_id in df['ds_anon_user_id'].unique():
  if len(df[df['ds_anon_user_id'] == user_id]) >= n+1:
    valid_user.append(user_id)
len(valid_user)
df = df[df.ds_anon_user_id.isin(valid_user)]

# group the data by user ids
grouped_data = df[['ds_anon_user_id', 'module','quizGrade',  'nsessions','meantimeToQuiz',
                   'ndays', 'npages','nactivities','timeInModule',
                  'endToQuiz','meanSessionDiff', 'pretestGrade',
                  'Nwords','Nactivities','Npages', 
                                    ]].groupby(['ds_anon_user_id']).apply(lambda r: (
                r['module'],
                r['nsessions'],
                np.array([r['meantimeToQuiz'],r['ndays'], r['npages'], r['nactivities'],r['timeInModule'],
                  r['endToQuiz'],r['meanSessionDiff'], r['pretestGrade'], r['nsessions'],r['quizGrade'],
                  r['Nwords'],r['Nactivities'],r['Npages'] ]).transpose()
                ))

from torch.utils.data import Dataset, DataLoader
class SPACE_DATASET(Dataset):
    def __init__(self, data, maxlength = 12):
        super(SPACE_DATASET, self).__init__()
        self.maxlength = maxlength
        self.data = data
        self.users = list()
        for user in data.index:
            self.users.append(user)

    def __len__(self):
        return len(self.users)
    
    def __getitem__(self, ix):
        user = self.users[ix]
        user = user
        module, labels, features = self.data[user]
        #0s should be used as padding values
        module = module.values 
        labels = labels.values

        # one hot encoding for target module id
        target_module_features = [0]*11
        target_module_features[module[self.maxlength]-1] = 1
        # append the other features of target module
        target_module_features.extend(features[self.maxlength][-4:-1])

        # get module ids and user interaction informations in the previous n modules
        module = module[0:self.maxlength]
        features = features[0:self.maxlength]

        # labels is the value we want to predict: the number of session 
        # the user is going to spend on the (n+1)_th module
        labels = np.array([labels[self.maxlength]])

        # change the type of variables so that they can be served as input to encoder layers
        module = torch.from_numpy(module).long()
        labels = torch.from_numpy(labels).float()
        features = torch.from_numpy(features).float()
        target_module_features = torch.from_numpy(np.array([target_module_features])).float()
        return module, labels,features, target_module_features

import torch
from sklearn.model_selection import train_test_split
train_data, test_data = train_test_split(grouped_data, test_size=0.1)
train_data, val_data = train_test_split(train_data, test_size=int(len(grouped_data)*0.1))
train_data = SPACE_DATASET(train_data, n)
val_data = SPACE_DATASET(val_data, n)
test_data = SPACE_DATASET(test_data, n)
train_dataloader = DataLoader(train_data, batch_size=64, shuffle=True)
val_dataloader = DataLoader(val_data, batch_size=64, shuffle=True)
test_dataloader = DataLoader(test_data, batch_size=64, shuffle=True)
item = train_data.__getitem__(0)

if torch.cuda.is_available():
    device = torch.device("cuda")
else:
    device = 'cpu'

import torch.nn as nn
import torch.nn.functional as f
from torch.nn import Embedding, Linear, MultiheadAttention, LayerNorm, Dropout

class Encoder(nn.Module):
    
    def __init__(self, module_size=12, features_size=13,module_feature_size=14, 
                 maxlength=12, num_heads=8, embedding_size=64, dropout = DROPOUT
                ):
        
        super(Encoder, self).__init__()
        self.input_length = maxlength
        # embedding layes and line layers
        self.embedding_module = Embedding(num_embeddings = module_size, 
                                        embedding_dim = embedding_size
                                       )

        self.linear_features = Linear(features_size, embedding_size)
        self.linear_module = Linear(module_feature_size, embedding_size)
             
        
        self.embedding_pos =  Embedding(    num_embeddings = maxlength,
                                            embedding_dim = embedding_size
                                           )        

        #attention
        self.attention  = MultiheadAttention(embed_dim = embedding_size,
                                             num_heads = num_heads,
                                             dropout = dropout)
        
        self.linear1 = Linear(embedding_size, embedding_size)
        self.linear2 = Linear(embedding_size, embedding_size)
        self.norm1 = LayerNorm(embedding_size)
        self.norm2 = LayerNorm(embedding_size)
        self.dropout1 = Dropout(dropout)
        
    def __call__(self, modules, features,target_module_features,block=False):
        
        if torch.cuda.is_available():
            device = torch.device("cuda")
        else:
            device = 'cpu'

        if block:

            module_ids = self.embedding_module(modules)
            features = self.linear_features(features)
            module_features = self.linear_module(target_module_features)
            
            # summation
            x = module_ids + features + module_features
        else:
            x = modules
        pos = torch.arange(self.input_length, device=device).unsqueeze(0)
        pos = self.embedding_pos(pos)
        x = x + pos
    
        x = x.permute(1, 0, 2)
        size = x.shape[0]
        x_1 = x
        # upper triangular attention mask (np.triu)
        x, _ = self.attention(x, x, x, 
                           attn_mask = torch.from_numpy( np.triu(np.ones((size, size)), k=1).astype('bool')).to(device))
        #skip connection
        x += x_1
        x =  x.permute(1, 0, 2) 
        x =  self.dropout1(x)
        return x

class SPACE(nn.Module):
    def __init__(self, num_encoders=4, embedding_size=64, maxlength=12, dropout=DROPOUT):
        super(SPACE, self).__init__()
        self.maxlength = maxlength
        self.embedding_size = embedding_size
        # stack of encoders
        self.encoders = nn.ModuleList([Encoder(embedding_size=embedding_size, maxlength=maxlength) for _ in range(num_encoders) ])
        # feed forward neural network
        self.linear1 = Linear(maxlength*embedding_size, int(maxlength*embedding_size/2))
        self.linear3 = Linear(int(maxlength*embedding_size/2), 1)
        self.dropout1 = Dropout(dropout)
        
    def __call__(self,module_id, features,target_module_features,batch=64):
        for ix, encoder in enumerate(self.encoders):
            if ix == 0:
                x = encoder(module_id, features,target_module_features, block=True)
            else:
                x = encoder(x, _, _)
        if batch>1:
            x = x.reshape(batch, self.embedding_size*self.maxlength )
            
        else:
            x = x.view(-1)
        x = self.linear1(self.dropout1(F.relu(x)))
        x =  self.linear3(x)
        return x

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
space = SPACE(maxlength=n, embedding_size=64)
epochs = 50
criterion = nn.MSELoss()
optimizer = torch.optim.Adam(space.parameters(), lr=0.0001, betas=(0.9, 0.999), eps=1e-8)
space.to(device)
criterion.to(device)

from tqdm import tqdm
import torch.nn.functional as F
from sklearn.metrics import r2_score, mean_absolute_error
def train_epoch(model=space, train_iterator=train_dataloader, optim=optimizer, criterion=criterion, device=device):
    model.train()

    train_loss = []
    num_corrects = 0
    num_total = 0
    labels = []
    outs = []
    tbar = tqdm(train_iterator)
    for item in tbar:
        module_ids = item[0].to(device).long()
        label = item[1].to(device).float()
        features = item[2].to(device).float()
        target_module_features = item[3].to(device).float()

        optim.zero_grad()
        output = model(module_ids,  features,target_module_features,batch = module_ids.shape[0])
        output = torch.reshape(output, label.shape)    
        loss = criterion(output, label)
        outs.extend(output.view(-1).data.cpu().numpy())
        labels.extend(label.view(-1).data.cpu().numpy())
        loss.backward()
        optim.step()
        train_loss.append(loss.item())
        
        tbar.set_description(
            'train mse - {:.4f} train r2 - {:.4f} train mae - {:.4f}'.format(loss, 
                                                                             r2_score(label.view(-1).data.cpu().numpy(), output.view(-1).data.cpu().numpy())
                                                                             ,mean_absolute_error(label.view(-1).data.cpu().numpy(), output.view(-1).data.cpu().numpy())))
        
    loss = np.mean(train_loss)
    r2 = r2_score(labels, outs)
    mae = mean_absolute_error(labels, outs)
    return loss, r2, mae,labels, outs

def val_epoch(model=space, val_iterator=val_dataloader,
              criterion=criterion, device=device):
    model.eval()

    val_loss = []
    labels = []
    outs = []
    tbar = tqdm(val_iterator)
    for item in tbar:
        module_ids = item[0].to(device).long()
        label = item[1].to(device).float()
        features = item[2].to(device).float()
        target_module_features = item[3].to(device).float()
        with torch.no_grad():
            output = model(module_ids,features,target_module_features, batch = module_ids.shape[0])
        output = torch.reshape(output, label.shape)
        loss = criterion(output, label)
        val_loss.append(loss.item())
        outs.extend(output.view(-1).data.cpu().numpy())
        labels.extend(label.view(-1).data.cpu().numpy())
        tbar.set_description('valid mse - {:.4f} r2 - {:.4f} mae - {:.4f}'.format(loss, 
                                                                      r2_score(label.view(-1).data.cpu().numpy(), output.view(-1).data.cpu().numpy())
                                                                       ,mean_absolute_error(label.view(-1).data.cpu().numpy(), output.view(-1).data.cpu().numpy())))
                             
    return np.average(val_loss), r2_score(labels, outs), mean_absolute_error(labels, outs),labels, outs

for epoch in range(epochs):
    train_loss, r2 ,mae, train_labels, train_outputs = train_epoch(model = space, device=device)
    print("epoch - {} train_loss - {:.2f} r2 - {:.2f} mae - {:.2f}".format(epoch, train_loss, r2,mae))
    val_loss, r2, mae, valid_labels, val_outputs = val_epoch(model = space, device=device)
    print("epoch - {} val_loss - {:.2f} r2 - {:.2f} mae - {:.2f}".format(epoch, val_loss, r2,mae))

    # we choose the model with best validation performance
    if val_loss < bestmse:
        bestmse = val_loss
        bestmae = mae
        bestr2 = r2
        torch.save(space, 'best_model.h5')

best_model = torch.load('best_model.h5')

"""# Result"""

print(df['nsessions'].std())

train_loss, r2, mae, train_labels, train_outputs = val_epoch(model = best_model, val_iterator = train_dataloader, device=device)
val_loss, r2,mae,val_labels, val_outputs = val_epoch(model = best_model, val_iterator = val_dataloader, device=device)
test_loss, r2, mae, test_labels, test_outputs = val_epoch(model = best_model, val_iterator = test_dataloader, device=device)

test_exp_pred = np.expm1(test_outputs)
test_exp_label = np.expm1(test_labels)
test_rmse = np.sqrt(np.mean((test_exp_pred-test_exp_label)**2))

train_exp_pred = np.expm1(train_outputs)
train_exp_label = np.expm1(train_labels)
train_rmse = np.sqrt(np.mean((train_exp_pred-train_exp_label)**2))

val_exp_pred = np.expm1(val_outputs)
val_exp_label = np.expm1(val_labels)
val_rmse = np.sqrt(np.mean((val_exp_pred-val_exp_label)**2))
print("The metric for ", n, " are: ") 
print("TRAIN_RMSE:  %.3f\n VAL_RMSE:  %.3f\n TEST_RMSE: %.3f" % (train_rmse, val_rmse, test_rmse))

import matplotlib.pyplot as plt
fig = plt.figure(figsize = (10, 10))
ax1 = fig.add_subplot(111)

ax1.scatter(list(range(len(test_labels))), test_exp_label, s=10, c='b', marker="s", label='labels')
ax1.scatter(list(range(len(test_outputs))),test_exp_pred, s=10, c='r', marker="o", label='predictions')
plt.legend(loc='upper left')
plt.show()

