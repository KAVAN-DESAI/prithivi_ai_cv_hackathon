# -*- coding: utf-8 -*-
"""CV Hackathon ResNet PyTorch.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1cWGeUbuHEB_B5XjiR_vnwQYh5My8npy8
"""

from google.colab import drive
drive.mount('/content/drive')


# DATA MANIPULATION AND STANDARD LIBRARIES
import os
import numpy as np 
import pandas as pd 
from datetime import datetime
import time
import random
from tqdm.autonotebook import tqdm


# TORCH
import torch
import torch.nn as nn
from torch.utils.data import Dataset,DataLoader
from torch.utils.data.sampler import SequentialSampler, RandomSampler

# SKLEARN
from sklearn.model_selection import StratifiedKFold

#CV
import cv2


import sys

#Albumenatations
import albumentations as A
import matplotlib.pyplot as plt
from albumentations.pytorch.transforms import ToTensorV2

#Glob
from glob import glob

class AverageMeter(object):
    """Computes and stores the average and current value"""
    def __init__(self):
        self.reset()

    def reset(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def update(self, val, n=1):
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count


# READING AND ADJUSTING THE DATA
folder_name = 'drive/MyDrive/CV Hackathon/Training Data/'
defects = pd.read_csv(folder_name+'Labels/Train_DefectType_PrithviAI.csv')
bbox = pd.read_csv(folder_name+'Labels/Train_DefectBoxes_PrithviAI.csv')
bbox.rename(columns = {'  image_id':'image_id','X':'x','Y':'y','W':'w','H':'h'},inplace=True)


# CONVERTING THE COORDINATES, ACCORDING TO THE DIMENSION OF THE FRAMES
bbox['x']*=4096    
bbox['w']*=4096
bbox['h']*=1000
bbox['y']*= 1000
DIR_TRAIN = folder_name+'Images Unzipped/Images/'


# CONSIDERING ONLY THOSE IMAGES WHICH EXISTS    
def func(x):
  if os.path.exists(x):
      return 1
  return 0
bbox['shape'] = bbox['image_id'].apply(lambda x: func(DIR_TRAIN+str(x)))
bbox = bbox[bbox['shape']!=0]


# IF MORE THAN ONE BOUNDING BOX EXIST, REMOVE IT
bbox = bbox.drop_duplicates(subset = ['image_id'])

image = cv2.imread(DIR_TRAIN+bbox['image_id'].values[0])
temp = bbox[['x','y','w','h']].values[0]
temp[2:]/=2
d_box= list(map(int,temp))
from google.colab.patches import cv2_imshow
cv2.rectangle(image,(d_box[0]-d_box[2],d_box[1]-d_box[3]),(d_box[0]+d_box[2],d_box[1]+d_box[3]),(220,0,0),2)
cv2_imshow(image)

# IMPLEMENTED FOR DETR HOWEVER, WE JUST MODIFIED THE CODE, SO THAT IT WORKS FOR THE RESNET PART AS WELL

n_folds = 5
seed = 42
null_class_coef = 0.5
num_classes = 1
num_queries = 10
BATCH_SIZE = 4
LR = 5e-5
lr_dict = {'backbone':0.1,'transformer':1,'embed':1,'final': 5}
EPOCHS = 2
max_norm = 0
model_name = 'detr_resnet50'


# FOR CREATING REPEATABLE RESULTS
def seed_everything(seed):
    random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = True
seed_everything(seed)
device = 'cuda' if torch.cuda.is_available() else 'cpu'

# CREATING FOLDS
skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)
df_folds = bbox[['image_id']].copy()
df_folds.loc[:, 'bbox_count'] = 1
df_folds = df_folds.groupby('image_id').count()
df_folds.loc[:, 'stratify_group'] = df_folds['bbox_count'].apply(lambda x: f'{x // 15}').values.astype(str)
df_folds.loc[:, 'fold'] = 0
for fold_number, (train_index, val_index) in enumerate(skf.split(X=df_folds.index, y=df_folds['stratify_group'])):
    df_folds.loc[df_folds.iloc[val_index].index, 'fold'] = fold_number


#IMAGE AUGMENTATION
def get_train_transforms():
    return A.Compose(
        [        
            A.ToGray(p=0.01),  
            ToTensorV2(p=1.0),
            
        ], 
        p=1.0,         
        bbox_params=A.BboxParams(format='coco',min_area=0, min_visibility=0,label_fields=['labels'])
        )

def get_valid_transforms():
    return A.Compose([
                      ToTensorV2(p=1.0),
                      ], 
                      p=1.0, 
                      bbox_params=A.BboxParams(format='coco',min_area=0, min_visibility=0,label_fields=['labels'])
                      )

# GROUPBY WAS USED FOR DETR, CONTAINING MULTIPLE BOUNDING BOX, HOWEVER WE USED IT IN THE CASE OF RESNET
 
image_data = bbox.groupby('image_id')
images = bbox['image_id'].values
DIR_TRAIN = folder_name+'Images Unzipped/Images/'


# CREATING A DICTIONARY SO THAT, WHEN LOADING THE DATA, EVERYTHING CANBE OBTAINED FROM ONE PLACE
def get_data(img_id):
    if img_id not in image_data.groups:
        return dict(image_id=img_id, source='', boxes=list())
    
    data  = image_data.get_group(img_id)
    boxes = data[['x','y','w','h']].values
    return dict(image_id = img_id, boxes = boxes,labels = 0)
image_list = [get_data(img_id) for img_id in tqdm(images) if os.path.exists(DIR_TRAIN+str(img_id))]

# PRINTING THE NULL IMAGES

print(f'total number of images: {len(image_list)}, images with bboxes: {len(image_data)}')
null_images=[x['image_id'] for x in image_list if len(x['boxes'])==0]
len(null_images)

DIR_TRAIN = folder_name+'Images Unzipped/Images/'


# CREATING A PYTORCH DATASET
class DefectDataset(Dataset):
    def __init__(self,image_ids,transforms=None):
        self.images = image_ids
        self.transforms = transforms
        self.img_ids = {x['image_id']:i for i,x in enumerate(image_list)}
    def get_indices(self,img_ids):
        return [self.img_ids[x] for x in img_ids]
        
    def __len__(self) -> int:
        return len(self.images)
    
    def __getitem__(self,index):
        record = self.images[index]
        image_id = record['image_id']

        image = cv2.imread(DIR_TRAIN+image_id, cv2.IMREAD_COLOR)
        #image = cv2.resize(image,IMAGE_SIZE)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).astype(np.float32)
        image /= 255.0
        # DETR takes in data in coco format 
        boxes = record['boxes'] 
        
        labels =  np.zeros(len(boxes), dtype=np.int32)
        if self.transforms:
            sample = {
                'image': image,
                'bboxes': boxes,
                'labels': labels
            }
            sample = self.transforms(**sample)
            image  = sample['image']
            boxes  = sample['bboxes']
            labels = sample['labels']

        _,h,w = image.shape

        # NORMALIZING BOUNDING BOX
        boxes = A.augmentations.bbox_utils.normalize_bboxes(sample['bboxes'],rows=h,cols=w)
        if len(boxes)>0:
            boxes = np.array(boxes)
            boxes[:,2:] /= 2
        else:
            boxes = np.zeros((0,4))
    
        target = {}
        target['boxes'] = torch.as_tensor(boxes,dtype=torch.float32)
        
        return image,target['boxes']

train_ds = DefectDataset(image_list,get_train_transforms())
valid_ds = DefectDataset(image_list,get_valid_transforms())


# VISUALIZING THE EXAMPLE
def show_example(image,target,image_id=None):
    box = target.cpu().numpy()[0]
    _,h,w = image.shape
    image = image.permute(1,2,0)
    box = A.augmentations.bbox_utils.denormalize_bbox(box,h,w)
    box =list(map(int,box))
    fig, ax = plt.subplots(1, 1,figsize=(30,30))
    image = image.cpu().numpy()
    cv2.rectangle(image,(box[0]-box[2],box[1]-box[3]),(box[0]+box[2],box[1]+box[3]),(220,0,0),2)
    ax.set_axis_off()
    ax.imshow(image)
    ax.set_title(image_id)
    plt.show()
show_example(*train_ds[10])



# CODE FOR CREATING RESNET MODEL

class ResNetModel(nn.Module):
    def __init__(self,num_classes = 4):
        super(ResNetModel,self).__init__()
        self.num_classes = num_classes
        import torchvision.models as models
        self.model = models.resnet18().to('cuda')
        self.out = nn.Linear(in_features=1000,out_features=4).to('cuda')
    def forward(self,images):
        d = self.model(images)
        d = d.squeeze()
        d = self.out(d)
        return d

'''

THE BELOW MENTIONED THINGS WERE SUPPOSED TO BE USED FOR DETR

matcher = HungarianMatcher(cost_giou=2,cost_class=1,cost_bbox=5)

weight_dict = {'loss_ce': 1, 'loss_bbox': 5 , 'loss_giou': 2}

losses = ['labels', 'boxes', 'cardinality']



'''
def collate_fn(batch):
    return tuple(zip(*batch))

# FUNCTION FOR CREATING THE TRAINING AND VALIDATION DATASET

def get_fold(fold):
    
    train_indexes = train_ds.get_indices(df_folds[df_folds['fold']!=fold].index.values)
    valid_indexes = valid_ds.get_indices(df_folds[df_folds['fold']==fold].index.values)
    
    train_data_loader = DataLoader(
        torch.utils.data.Subset(train_ds,train_indexes),
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=0,
        collate_fn=collate_fn
    )

    valid_data_loader = DataLoader(
        torch.utils.data.Subset(valid_ds,valid_indexes),
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=0,
        collate_fn=collate_fn
    )
    return train_data_loader,valid_data_loader

def train_fn(data_loader,model,criterion,optimizer,device,scheduler,epoch):
    model.train()
    criterion.train()
    
    '''
        Returns the total training loss
    '''

    tk0 = tqdm(data_loader, total=len(data_loader),leave=False)
    log = None
    total_train_loss = 0
    for step, (images, targets) in enumerate(tk0):
        batch_size = len(images)
        images = torch.from_numpy(np.array([x.cpu().numpy() for x in images])).to(device)
        targets = torch.from_numpy(np.array([x.cpu().numpy() for x in images])).to(device)
        output = model(images)
        total_loss = criterion(output, targets)
        
        optimizer.zero_grad()
        total_loss.backward()
        
        if max_norm > 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm)
        
        optimizer.step()
        
        if scheduler is not None:
            scheduler.step()
        total_train_loss+=total_loss
    return total_train_loss

def eval_fn(data_loader, model,criterion, device):

    '''
        Returns the total validation loss
    '''    

    model.eval()
    criterion.eval()
    total_val_loss = 0
    with torch.no_grad():
        
        tk0 = tqdm(data_loader, total=len(data_loader),leave=False)
        for step, (images,image_ids) in enumerate(tk0):
            
            batch_size = len(images)
            batch_size = len(images)
            output = model(images)
        
            loss_dict = criterion(image_ids, output)
            total_val_loss+=loss_dict
    return total_val_loss
        
        

import json 
def run(fold,epochs=EPOCHS):
    train_data_loader,valid_data_loader = get_fold(fold)
    model = ResNetModel(num_classes=num_classes)
    model = model.to(device)
    criterion = torch.nn.MSELoss()
    criterion = criterion.to(device)
    optimizer = torch.optim.AdamW(model.parameters())
    
    best_loss = 100
    header_printed = False
    for epoch in range(epochs):
        train_loss = train_fn(train_data_loader, model,criterion, optimizer,device,scheduler=None,epoch=epoch)
        val_loss = eval_fn(valid_data_loader, model,criterion, device)

        if best_loss > val_loss:
            best_loss = val_loss
            torch.save(model.state_dict(), f'drive/MyDrive/CV Hackathon FIles/detr_best_{fold}.pth')

import gc
gc.collect()

run(fold=0)
