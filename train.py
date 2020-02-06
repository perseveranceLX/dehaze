# coding=utf-8
import argparse
import os
import urllib.request
import numpy as np
import torch
from torch import nn, optim
from torch.backends import cudnn
from torch.autograd import Variable
from torch.utils.data import DataLoader
from torchvision.transforms import Compose, ToTensor, Resize, Normalize, CenterCrop, RandomCrop
from tensorboardX import SummaryWriter
from torchvision.utils import make_grid

from data import DatasetFromFolder, DatasetFromFolder_2
from model.net2 import net as Net
from utils import save_checkpoint

parser = argparse.ArgumentParser(description="PyTorch DeepDehazing")
parser.add_argument("--name", type=str, help="path to save train log")
parser.add_argument("--train", default="../ITS_data/train", type=str,
                    help="path to load train datasets(default: none)")
parser.add_argument("--test", default="../ITS_data/test", type=str,
                    help="path to load test datasets(default: none)")
parser.add_argument("--batchSize", type=int, default=10, help="training batch size")
parser.add_argument("--nEpochs", type=int, default=300, help="number of epochs to train for")
parser.add_argument("--lr", type=float, default=1e-4, help="Learning Rate. Default=1e-4")
parser.add_argument("--step", type=int, default=1000, help="step to test the model performance. Default=2000")
parser.add_argument("--cuda",type=str, default="Ture", help="Use cuda?")
parser.add_argument("--gpus", type=int, default=1, help="nums of gpu to use")
parser.add_argument("--resume", default="", type=str, help="Path to checkpoint (default: none)")
parser.add_argument("--start-epoch", default=1, type=int, help="Manual epoch number (useful on restarts)")
parser.add_argument("--threads", type=int, default=8, help="Number of threads for data loader to use, Default: 1")
parser.add_argument("--momentum", default=0.9, type=float, help="Momentum, Default: 0.9")
parser.add_argument("--pretrained", default="", type=str, help="path to pretrained model (default: none)")
#parser.add_argument("--pretrained", default="", type=str, help="path to pretrained model (default: none)")
parser.add_argument("--checkpoints", default="../new/", type=str, help="path to save networks")
parser.add_argument("--report", default=False, type=bool, help="report to wechat")


def main():
    global opt, logger, model, criterion
    opt = parser.parse_args()
    print(opt)

    logger = SummaryWriter(opt.name)

    cuda = opt.cuda
    if cuda and not torch.cuda.is_available():
        raise Exception("No GPU found, please run without --cuda")

    seed = 1334
    torch.manual_seed(seed)
    if cuda:
        torch.cuda.manual_seed(seed)

    cudnn.benchmark = True

    print("==========> Loading datasets")

    train_dataset = DatasetFromFolder(opt.train, transform=Compose([
        ToTensor()
    ]))

    indoor_test_dataset = DatasetFromFolder_2(opt.test, transform=Compose([
        ToTensor()
    ]))

    training_data_loader = DataLoader(dataset=train_dataset, num_workers=opt.threads, batch_size=opt.batchSize,
                                      pin_memory=True, shuffle=True)
    indoor_test_loader = DataLoader(dataset=indoor_test_dataset, num_workers=opt.threads, batch_size=1, pin_memory=True,
                                    shuffle=True)

    print("==========> Building model")
    model = Net()
    criterion = nn.MSELoss(size_average=True)

    #print(model)

    # optionally resume from a checkpoint
    if opt.resume:
        if os.path.isfile(opt.resume):
            print("=> loading checkpoint '{}'".format(opt.resume))
            checkpoint = torch.load(opt.resume)
            opt.start_epoch = checkpoint["epoch"] #opt.start_epoch = checkpoint["epoch"] // 2 + 1
            model.load_state_dict(checkpoint["state_dict"])
        else:
            print("=> no checkpoint found at '{}'".format(opt.resume))

    # optionally copy weights from a checkpoint
    if opt.pretrained:
        if os.path.isfile(opt.pretrained):
            print("=> loading model '{}'".format(opt.pretrained))
            weights = torch.load(opt.pretrained)
            model.load_state_dict(weights['state_dict'])
        else:
            print("=> no model found at '{}'".format(opt.pretrained))

    print("==========> Setting GPU")
    #if cuda:
    if opt.cuda:
        model = nn.DataParallel(model, device_ids=[i for i in range(opt.gpus)]).cuda()
        criterion = criterion.cuda()
    else:
        model = model.cpu()
        criterion = criterion.cpu()

    print("==========> Setting Optimizer")
    optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=opt.lr)

    print("==========> Training")
    for epoch in range(opt.start_epoch, opt.nEpochs + 1):
        train(training_data_loader, indoor_test_loader, optimizer, epoch)


def train(training_data_loader, indoor_test_loader, optimizer, epoch):
    print("epoch =", epoch, "lr =", optimizer.param_groups[0]["lr"])

    for iteration, batch in enumerate(training_data_loader, 1):
        model.train()
        model.zero_grad()
        optimizer.zero_grad()

        steps = len(training_data_loader) * (epoch-1) + iteration

        data, label, label2, label3, label4, label5 = \
            Variable(batch[0]), \
            Variable(batch[1], requires_grad=False), \
            Variable(batch[2], requires_grad=False), \
            Variable(batch[3], requires_grad=False), \
            Variable(batch[4], requires_grad=False), \
            Variable(batch[5], requires_grad=False)


        if opt.cuda:
            data = data.cuda()
            label = label.cuda()
            label2 = label2.cuda()
            label3 = label3.cuda()
            label4 = label4.cuda()
            label5 = label5.cuda()
        else:
            data = data.cpu()
            label = label.cpu()
            label2 = label2.cpu()
            label3 = label3.cpu()
            label4 = label4.cpu()
            label5 = label5.cpu()

        output = model(data)
        loss1 = criterion(output[0], label)
        # loss2 = criterion(output[1], label2)
        # loss3 = criterion(output[2], label3)
        # loss4 = criterion(output[3], label4)
        # loss5 = criterion(output[4], label5)
        #
        # loss = loss1 + loss2 + loss3 + loss4 + loss5
        # loss = loss1 + 0.2*loss2 + 0.1*loss3 + 0.1*loss4 + 0.1*loss5
        # loss = loss1
        loss = loss1
        loss.backward()

        optimizer.step()

        if iteration % 10 == 0:
            # print("===> Epoch[{}]({}/{}): Loss: {:.6f} | loss1: {:.6f} | loss2: {:.6f} | loss3: {:.6f} | loss4: {:.6f} | loss5: {:.6f}".format(epoch, iteration, len(training_data_loader),
            #                                                    loss.item(), loss1.item(), loss2.item(), loss3.item(), loss4.item(), loss5.item()))

            print("===> Epoch[{}]({}/{}): Loss: {:.6f}".format( epoch, iteration, len(training_data_loader), loss.item()))

            logger.add_scalar('loss', loss.item(), steps)
            # logger.add_scalar('loss1', loss1.item(), steps)
            # logger.add_scalar('loss2', loss2.item(), steps)
            # logger.add_scalar('loss3', loss3.item(), steps)
            # logger.add_scalar('loss4', loss4.item(), steps)
            # logger.add_scalar('loss5', loss5.item(), steps)


        # if iteration % opt.step == 0:
        #     data_temp = make_grid(data.data)
            # label_temp = make_grid(label.data)
            # output_temp = make_grid(output[0].data)

            # logger.add_image('data_temp', data_temp, steps)
            # logger.add_image('label_temp', label_temp, steps)
            # logger.add_image('output_temp', output_temp, steps)

        if iteration % opt.step == 0:
            save_checkpoint(model, steps // opt.step, opt.checkpoints)
            test(indoor_test_loader, steps // opt.step)
            # if steps // opt.step == 4:
            #     lr = opt.lr/10
            #     for param_group in optimizer.param_groups:
            #         param_group['lr'] = lr

def test(test_data_loader, epoch):
    psnrs = []
    mses = []
    for iteration, batch in enumerate(test_data_loader, 1):
        model.eval()
        data, label = \
            Variable(batch[0], volatile=True), \
            Variable(batch[1])

        if opt.cuda:
            data = data.cuda()
            label = label.cuda()
        else:
            data = data.cpu()
            label = label.cpu()

        output = torch.clamp(model(data)[0], 0., 1.)
        # print(output)
        mse = nn.MSELoss()(output, label)
        mses.append(mse.item())
        psnr = 10 * np.log10(1.0 / mse.item())
        psnrs.append(psnr)
    psnr_mean = np.mean(psnrs)
    mse_mean = np.mean(mses)

    print("Vaild  epoch test1 %d psnr: %f" % (epoch, psnr_mean))
    file = open('its-c.txt', 'a+')
    file.write(str([epoch, ' psnr: ', psnr_mean]))
    file.write('\n')
    file.close()


    logger.add_scalar('psnr', psnr_mean, epoch)
    logger.add_scalar('mse', mse_mean, epoch)

    data = make_grid(data.data)
    label = make_grid(label.data)
    output = make_grid(output.data)

    logger.add_image('data', data, epoch)
    logger.add_image('label', label, epoch)
    logger.add_image('output', output, epoch)

# def adjust_learning_rate(optimizer, epoch):
#     """Sets the learning rate to the initial LR decayed by 10 every 30 epochs"""
#
#     args.lr = args.original_lr
#
#     for i in range(len(args.steps)):
#
#         scale = args.scales[i] if i < len(args.scales) else 1
#
#         if epoch >= args.steps[i]:
#             args.lr = args.lr * scale
#             if epoch == args.steps[i]:
#                 break
#         else:
#             break
#     for param_group in optimizer.param_groups:
#         param_group['lr'] = args.lr


if __name__ == "__main__":
    os.system('clear')
    main()
