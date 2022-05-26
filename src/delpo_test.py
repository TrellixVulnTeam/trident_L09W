import os
import argparse
import json
import numpy as np
from torch._C import device

import tqdm
import torch
from torch import nn

from src.utils2 import Profiler
from src.zoo.delpo_utils import inner_adapt_delpo, setup

#import wandb

#wandb.init(project="meta", entity='anujinho', config={})

##############
# Parameters #
##############

parser = argparse.ArgumentParser()
parser.add_argument('--cnfg', type=str)
parser.add_argument('--dataset', type=str)
parser.add_argument('--root', type=str)
parser.add_argument('--model-path', type=str)
parser.add_argument('--backbone', type=list)
parser.add_argument('--n-ways', type=int)
parser.add_argument('--k-shots', type=int)
parser.add_argument('--q-shots', type=int)
parser.add_argument('--inner-adapt-steps-test', type=int)
parser.add_argument('--inner-lr', type=float)
parser.add_argument('--meta-lr', type=float)
parser.add_argument('--wt-ce', type=float)
parser.add_argument('--klwt', type=str)
parser.add_argument('--rec-wt', type=float)
parser.add_argument('--beta-l', type=float)
parser.add_argument('--beta-s', type=float)
parser.add_argument('--task_adapt', type=str)
parser.add_argument('--experiment', type=str)
parser.add_argument('--order', type=str)
parser.add_argument('--device', type=str)
parser.add_argument('--download', type=str)
parser.add_argument('--repar', type=str, default=True)
parser.add_argument('--times', type=int)
parser.add_argument('--extra', type=str)


args = parser.parse_args()
with open(args.cnfg) as f:
    parser = argparse.ArgumentParser()
    argparse_dict = vars(args)
    argparse_dict.update(json.load(f))

    args = argparse.Namespace()
    args.__dict__.update(argparse_dict)


# TODO: fix this bool/str shit

if args.order == 'True':
    args.order = True
elif args.order == 'False':
    args.order = False

if args.download == 'True':
    args.download = True
elif args.download == 'False':
    args.download = False

if args.klwt == 'True':
    args.klwt = True
elif args.klwt == 'False':
    args.klwt = False

if args.task_adapt == 'True':
    args.task_adapt = True
elif args.task_adapt == 'False':
    args.task_adapt = False

if args.backbone[0] == 'True':
    args.backbone[0] = True
elif args.backbone[0] == 'False':
    args.backbone[0] = False

# wandb.config.update(args)

# Generating Tasks, initializing learners, loss, meta - optimizer and profilers
_, _, test_tasks, _ = setup(
    args.dataset, args.root, args.n_ways, args.k_shots, args.q_shots, args.order, args.inner_lr, args.device, download=args.download, task_adapt=args.task_adapt, task_adapt_fn=args.task_adapt_fn, args=args)
reconst_loss = nn.MSELoss(reduction='none')
if args.order == False:
    profiler = Profiler('DELPO_test_{}_{}-way_{}-shot_{}-queries'.format(args.dataset,
                        args.n_ways, args.k_shots, args.q_shots), args.experiment, args)

elif args.order == True:
    profiler = Profiler('FO-DELPO_{}_{}-way_{}-shot_{}-queries'.format(
        args.dataset, args.n_ways, args.k_shots, args.q_shots), args.experiment, args)


## Testing ##

for model_name in os.listdir(args.model_path):
    learner = torch.load('{}/{}'.format(args.model_path, model_name))
    learner = learner.to(args.device)
    print('Testing on held out classes')
    for t in range(args.times):
        for i, tetask in enumerate(test_tasks):
            # wandb.define_metric("accuracies", summary="max")
            # wandb.define_metric("accuracies", summary="mean")

            model = learner.clone()
            #tetask = test_tasks.sample()
            if args.extra == 'Yes':
                evaluation_loss, evaluation_accuracy, reconst_img, query_imgs, mu_l, log_var_l, mu_s, log_var_s, logits, labels, mu_l_0, log_var_l_0, mu_s_0, log_var_s_0 = inner_adapt_delpo(
                    tetask, reconst_loss, model, args.n_ways, args.k_shots, args.q_shots, args.inner_adapt_steps_test, args.device, True, args)
            elif args.extra == 'No':
                evaluation_loss, evaluation_accuracy, reconst_img, query_imgs, mu_l, log_var_l, mu_s, log_var_s, logits, labels = inner_adapt_delpo(
                    tetask, reconst_loss, model, args.n_ways, args.k_shots, args.q_shots, args.inner_adapt_steps_test, args.device, True, args)

            # Logging test-task logits and ground-truth labels
            tmp = np.array(torch.cat([torch.full((args.n_ways*args.q_shots, 1), i), logits, labels.unsqueeze(dim=1)], axis=1))
            profiler.log_csv(tmp, 'preds')
            
            # Logging per test-task losses and accuracies
            tmp = [i, evaluation_accuracy.item()]
            tmp = tmp + [a.item() for a in evaluation_loss.values()]
            tmp = tmp + [model_name]
            profiler.log_csv(tmp, 'test_all') if args.times > 1 else profiler.log_csv(tmp, 'test')

            # Logging test-task images and latents
            di = {"reconst_examples": reconst_img, "gt_examples": query_imgs}
            profiler.log_data(di, iter, 'images', 'test')
            profiler.log_data(dl, iter, 'latents', 'test')

            # Logging latents before and after adaptation
            if args.extra == 'Yes':
                dl_0 = {"label_latents": [mu_l_0, log_var_l_0],
                  "style_latents": [mu_s_0, log_var_s_0]}
                profiler.log_data(dl_0, i, 'latents_0', 'test')

                dl = {"label_latents": [mu_l, log_var_l],
                    "style_latents": [mu_s, log_var_s]}
                profiler.log_data(dl, i, 'latents', 'test')  

            # wandb.log(dict({f"test/{key}": loss.item() for _, (key, loss) in enumerate(evaluation_loss.items())},
            #             **{'test/accuracies': evaluation_accuracy.item(), 'test/task': i}))
