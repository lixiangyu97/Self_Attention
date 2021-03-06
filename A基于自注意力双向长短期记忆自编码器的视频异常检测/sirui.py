from __future__ import print_function
import argparse
import torch
import torchvision
import torch.utils.data
import torch.nn as nn
import torch.optim as optim
from torch.autograd import Variable
from torchvision.models import vgg16
from torch.utils.data import Dataset, DataLoader
from torchvision import datasets, transforms, models
import numpy as np
import ast
from torch.nn import functional as F
from math import log10
import random
import torch.utils.data
import torch.backends.cudnn as cudn
import argparse
import pickle
from biconvlstm import *
import pytorch_msssim
#import pytorch_ssim
from atten import *
from spec import *
class Encoder(torch.nn.Module):
    def __init__(self, t_length=5, n_channel=3):
        super(Encoder, self).__init__()

        def Basic(intInput, intOutput):
            return torch.nn.Sequential(
                torch.nn.Conv2d(in_channels=intInput, out_channels=intOutput, kernel_size=3, stride=1, padding=1),
                torch.nn.BatchNorm2d(intOutput),
                torch.nn.ReLU(inplace=False),
                torch.nn.Conv2d(in_channels=intOutput, out_channels=intOutput, kernel_size=3, stride=1, padding=1),
                torch.nn.BatchNorm2d(intOutput),
                torch.nn.ReLU(inplace=False)
            )

        def Basic_(intInput, intOutput):
            return torch.nn.Sequential(
                torch.nn.Conv2d(in_channels=intInput, out_channels=intOutput, kernel_size=3, stride=1, padding=1),
                torch.nn.BatchNorm2d(intOutput),
                torch.nn.ReLU(inplace=False),
                torch.nn.Conv2d(in_channels=intOutput, out_channels=intOutput, kernel_size=3, stride=1, padding=1),
            )

        self.moduleConv1 = Basic(n_channel * (t_length - 1), 64)
        self.modulePool1 = torch.nn.MaxPool2d(kernel_size=2, stride=2)

        self.moduleConv2 = Basic(64, 128)
        self.modulePool2 = torch.nn.MaxPool2d(kernel_size=2, stride=2)

        self.moduleConv3 = Basic(128, 256)
        self.modulePool3 = torch.nn.MaxPool2d(kernel_size=2, stride=2)

        self.moduleConv4 = Basic_(256, 512)
        self.moduleBatchNorm = torch.nn.BatchNorm2d(512)
        self.moduleReLU = torch.nn.ReLU(inplace=False)

    def forward(self, x):
        tensorConv1 = self.moduleConv1(x)
        tensorPool1 = self.modulePool1(tensorConv1)

        tensorConv2 = self.moduleConv2(tensorPool1)
        tensorPool2 = self.modulePool2(tensorConv2)

        tensorConv3 = self.moduleConv3(tensorPool2)
        tensorPool3 = self.modulePool3(tensorConv3)

        tensorConv4 = self.moduleConv4(tensorPool3)

        return tensorConv4, tensorConv1, tensorConv2, tensorConv3

class Decoder(torch.nn.Module):
    def __init__(self, t_length=5, n_channel=3):
        super(Decoder, self).__init__()

        def Basic(intInput, intOutput):
            return torch.nn.Sequential(
                torch.nn.Conv2d(in_channels=intInput, out_channels=intOutput, kernel_size=3, stride=1, padding=1),
                torch.nn.BatchNorm2d(intOutput),
                torch.nn.ReLU(inplace=False),
                torch.nn.Conv2d(in_channels=intOutput, out_channels=intOutput, kernel_size=3, stride=1, padding=1),
                torch.nn.BatchNorm2d(intOutput),
                torch.nn.ReLU(inplace=False)
            )

        def Gen(intInput, intOutput, nc):
            return torch.nn.Sequential(
                torch.nn.Conv2d(in_channels=intInput, out_channels=nc, kernel_size=3, stride=1, padding=1),
                torch.nn.BatchNorm2d(nc),
                torch.nn.ReLU(inplace=False),
                torch.nn.Conv2d(in_channels=nc, out_channels=nc, kernel_size=3, stride=1, padding=1),
                torch.nn.BatchNorm2d(nc),
                torch.nn.ReLU(inplace=False),
                torch.nn.Conv2d(in_channels=nc, out_channels=intOutput, kernel_size=3, stride=1, padding=1),
                torch.nn.Tanh()
            )

        def Upsample(nc, intOutput):
            return torch.nn.Sequential(
                torch.nn.ConvTranspose2d(in_channels=nc, out_channels=intOutput, kernel_size=3, stride=2, padding=1,
                                         output_padding=1),
                torch.nn.BatchNorm2d(intOutput),
                torch.nn.ReLU(inplace=False)
            )

        self.moduleConv = Basic(512, 512)
        self.moduleUpsample4 = Upsample(512, 256)

        self.moduleDeconv3 = Basic(512, 256)
        self.moduleUpsample3 = Upsample(256, 128)

        self.moduleDeconv2 = Basic(256, 128)
        self.moduleUpsample2 = Upsample(128, 64)

        self.moduleDeconv1 = Gen(128, n_channel, 64)

    def forward(self, x, skip1, skip2, skip3):
        tensorConv = self.moduleConv(x)

        tensorUpsample4 = self.moduleUpsample4(tensorConv)
        cat4 = torch.cat((skip3, tensorUpsample4), dim=1)

        tensorDeconv3 = self.moduleDeconv3(cat4)
        tensorUpsample3 = self.moduleUpsample3(tensorDeconv3)
        cat3 = torch.cat((skip2, tensorUpsample3), dim=1)

        tensorDeconv2 = self.moduleDeconv2(cat3)
        tensorUpsample2 = self.moduleUpsample2(tensorDeconv2)
        cat2 = torch.cat((skip1, tensorUpsample2), dim=1)

        output = self.moduleDeconv1(cat2)

        return output

class mymodel(nn.Module):
    def __init__(self,input_size,input_dim,hidden_dim,kernel_size,num_layers,bias=False,n_channel =3,  t_length = 5):
        super(mymodel,self).__init__()
        self.have_cuda = True
        self.height,self.width = input_size
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.kernel_size = kernel_size
        self.num_layers = num_layers
        self.bias = bias
        self.Encoder = Encoder(t_length,n_channel)
        self.Decoder = Decoder(t_length,n_channel)

        #self.ConvLSTM = ConvLSTM(input_size = (16,16),input_dim = 1024,hidden_dim = [512,256,128,64,32],kernel_size = (3,3),num_layers=5,#5?????????lstmbatch_first=True,bias = True)#????????? ????????????????????????
        '''height=width=256'''
        # self.Biconvlstm = BiConvLSTM(input_size = (32,32),
        #                          input_dim = 128,
        #                          hidden_dim = 128,
        #                          kernel_size = (3,3),
        #                          num_layers= 3,
        #                          bias = True)
        '''height=width=128(??????attention???????????????)'''
        self.Biconvlstm = BiConvLSTM(input_size=(16, 16),
                                     input_dim=128,
                                     hidden_dim=128,
                                     kernel_size=(3, 3),
                                     num_layers=3,
                                     bias=True)
        self.attn4 = Self_Attn(512, 'relu')
        self.attn3 = Self_Attn(256, 'relu')
        self.attn2 = Self_Attn(128, 'relu')
        self.attn1 = Self_Attn(64, 'relu')

        #self.prior = vgg16(pretrained=False).features[:-1]  # [:-1]??????????????????????????????????????????
        #self.encoder = vgg16(pretrained=False)
        # self.encoder.features[0] = nn.Conv2d(6, 64, kernel_size=(3, 3), stride=(1, 1), padding=(1, 1))  # ????????????????????????
        # self.encoder.features[23] = nn.MaxPool2d(kernel_size=1, stride=1, padding=0, dilation=1,
        #                                          ceil_mode=False)  # Size([8, 512, 32, 32])
        # self.encoder = self.encoder.features[:-1]
        # self.feature = vgg16(pretrained=False)
        # self.feature.features[23] = nn.MaxPool2d(kernel_size=1, stride=1, padding=0, dilation=1,
        #                                          ceil_mode=False)  # Size([8, 512, 32, 32])  ??????????????????????????????????????????????????????
        # self.feature = self.feature.features[:-1]

    def forward(self,x,train = True):
        fea, skip1, skip2, skip3 = self.Encoder(x)
        skip1 = self.attn1(skip1)
        skip2 = self.attn2(skip2)
        skip3 = self.attn3(skip3)

        if train:
            h = self.Biconvlstm(fea)
            #h = self.attn4(h)
            output = self.Decoder(h,skip1,skip2,skip3)
            return output
        else:
            h = self.Biconvlstm(fea)
            #h = self.attn4(h)
            out = self.Decoder(h,skip1,skip2,skip3)
            return out

def recons_loss(recon_x, x):
    # msssim ??????????????????????????????????????????????????????????????????????????????????????????????????????SSIM??????????????????????????????????????????
    
    msssim = ((1-pytorch_msssim.msssim(x,recon_x)))/2   #??????????????????ssim??????
    #ssim = ((1-pytorch_msssim.ssim(x,recon_x)))/2
    #????????????????????????????????????????????????????????????????????????????????????
    # ???????????????????????????????????????????????????????????????????????????????????????????????????????????? structural similarity ???????????????????????? MSE ???????????????????????????????????????????????????????????????
    f1 =  F.l1_loss(recon_x, x)  #l1?????????????????????????????????????????????????????????  l2?????????????????????????????? ?????????
    #L2????????????????????????????????????????????????????????????????????????2*2 ???0.1*0.1????????????L2???????????????????????????????????????
    #???????????? MS-SSIM+L1????????????????????????
    #?????????????????????????????????MS-SSIM????????????????????????????????????????????????????????????????????????????????????????????????????????????
    # ???L1???????????????????????????????????????????????????????????????????????0.84?????????????????????????????????G????????????????????????MS-SSIM??????????????????????????? Lmix = ??*Lmsssim + (1-??)*G*L1  G?????????????????????
    return f1+msssim
    #return f1




