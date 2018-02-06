#!/usr/bin/python
# -*- coding: utf-8 -*-

##
## run.py
##
## This script implements a unified mechanism to launch computations locally, on Sango cluster, and on K cluster.
## 
## Operations performed:
## 1. build custom parameterizations from commandline arguments
## 2. initialize a standalone directory per experiment to start, each containing a different 'modelParams.py'
## 3. launch the runs locally, on Sango, or on K clusters

# commandline argument parsing
import argparse
import sys

# guessing the number of cpu (for local execution)
import multiprocessing

# git misc info
import subprocess
import string

# load base and custom parameterizations
import importlib

# write run parameterization
import json

#import shlex
import os
import time


class JobDispatcher:

  def __init__(self, cmd_args):
    # In addition to the commandline arguments, the JobDispatcher object
    # contains timing info and the git status of the repository
    execTime = time.localtime()
    self.timeString = str(execTime[0])+'_'+str(execTime[1])+'_'+str(execTime[2])+'_'+str(execTime[3])+':'+str(execTime[4])
    self.cmd_args = cmd_args
    self.platform = cmd_args.platform
    self.interactive = cmd_args.interactive
    self.sim_counter = 0
    self.get_git_info()
    self.params = {} # will be filled later

  def get_git_info(self):
    # Retrieve info on the code version (git commit ID and git status), to ensure reproducibility
    # commit ID
    try:
      self.commit_id = subprocess.check_output(['git', 'rev-parse', 'HEAD'])
      self.commit_id = 'git commit ID = ' + self.commit_id[0:-1]
    except:
      self.commit_id = 'git commit ID not available'
    # git status
    try:
      self.status_line = subprocess.check_output(['git', 'status', '--porcelain', '-uno', '-z'])
      self.status_line = self.status_line.replace('\0', ' - ')
      if self.status_line == '':
        self.status_line = 'All changes have been commited'
      else:
        self.status_line = 'Changes not yet commited in the following files: '+self.status_line
    except:
      self.status_line = 'Git status not available'

  def load_base_config(self, base='baseParams'):
    # Loads the base parameterization, initializing all parameters to sensible defaults
    params = importlib.import_module(base).params
    self.params.update(params)

  def load_custom_config(self, custom):
    # Loads an optional .py file which specifies custom parameters
    # this file overrides the base parameters
    try:
      #params = importlib.import_module(custom).params # fails when in other directories
      exec(open(custom).read()) 
      self.params.update(params)
    except:
      raise ImportError('The custom parameters could not be loaded. Please make sure that the custom parameters are provided in a python file defining the variable "params".')

  def load_cmdline_config(self, cmd_args):
    # Loads the options from the commandline, overriding all previous parameterizations
    self.params.update({k: v for k, v in vars(cmd_args).items() if k in ['LG14modelID', 'whichTest', 'nbcpu', 'nbCh', 'email'] if v != None})

  def create_workspace(self, IDstring):
    # Initialize the experiment-specific directory named with IDstring and populate it with the required files
    print('Create subdirectory: '+IDstring)
    os.system('mkdir '+IDstring)
    os.system('cp LGneurons.py '+IDstring+'/')
    os.system('cp testFullBG.py '+IDstring+'/')
    os.system('cp testChannelBG.py '+IDstring+'/')
#    os.system('cp plot_tools.py '+IDstring+'/')
    os.system('cp solutions_simple_unique.csv '+IDstring+'/')
    os.system('cp __init__.py '+IDstring+'/')
    os.system('mkdir '+IDstring+'/log')

  def write_modelParams(self, IDstring, params):
    # Write the experiment-specific parameterization file into modelParams.py
    print 'Write modelParams.py'
    header = ['#!/apps/free/python/2.7.10/bin/python \n\n',
              '## This file was auto-generated by run.py called with the following arguments:\n',
              '# '+' '.join(sys.argv)+'\n\n',
              '## ID string of experiment:\n',
              '# '+IDstring+'\n\n',
              '## Reproducibility info:\n',
              '#  platform = '+self.platform+'\n'
              '#  '+self.commit_id+'\n',
              '#  '+self.status_line+'\n\n',
             ]
    paramsFile = open('modelParams.py','w')
    paramsFile.writelines(header)
    json_params = json.dumps(params, indent=4, separators=(',', ': '), sort_keys=True)
    json_params = json_params.replace(': true',': True').replace(': false', ': False').replace(': null', ': None') # more robust would be to use json.loads()
    paramsFile.writelines(['params =\\\n'])
    paramsFile.writelines(json_params)
    if self.interactive == True:
      paramsFile.writelines(['\n\ninteractive = True'])
    else:
      paramsFile.writelines(['\n\ninteractive = False'])
    paramsFile.close()

  def launchOneParameterizedRun(self, counter, params):
    # Generates the sub-directory and queue the run
    IDstring = self.timeString+'_%05d' % (counter)
    # 1: initialize the directory
    self.create_workspace(IDstring)
    os.chdir(IDstring)
    # 2: write the modelParams.py file
    self.write_modelParams(IDstring, params)
    # 3: specific actions for different platforms
    if self.platform == 'Local':
      ###################
      # LOCAL EXECUTION #
      ###################
      # just launch the script
      command = 'python '+params['whichTest']+'.py'
    elif self.platform == 'Sango':
      ###########################
      # SANGO CLUSTER EXECUTION #
      ###########################
      sango_header = '#!/bin/bash\n\n'
      # #SBATCH --mem-per-cpu=1G changed for #SBATCH --mem-per-cpu=200M
      slurmOptions = ['#SBATCH --time='+params['durationH']+':'+params['durationMin']+':00 \n',
                      '#SBATCH --partition=compute \n',
                      '#SBATCH --mem-per-cpu=1G \n',
                      '#SBATCH --ntasks=1 \n',
                      '#SBATCH --cpus-per-task='+str(params['nbcpu'])+' \n',
                      '#SBATCH --job-name=sBCBG_'+IDstring+'\n',
                      '#SBATCH --input=none\n',
                      '#SBATCH --output="'+IDstring+'.out" \n',
                      '#SBATCH --error="'+IDstring+'.err" \n',
                      '#SBATCH --mail-user='+params['email']+'\n',
                      '#SBATCH --mail-type=BEGIN,END,FAIL \n',
                      ]
      moduleUse = ['module use /apps/unit/DoyaU/.modulefiles/ \n']
      #moduleLoad = ['module load nest/2.12.0 \n']
      moduleLoad = ['module load nest/2.10 \n']
      # write the script file
      print 'Write slurm script file'
      script = open('go.slurm','w')
      script.writelines(sango_header)
      script.writelines(slurmOptions)
      script.writelines(moduleUse)
      script.writelines(moduleLoad)
      script.writelines('time srun --mpi=pmi2 python '+params['whichTest']+'.py \n')
      script.close()
      # execute the script file
      command = 'sbatch go.slurm'
    elif self.platform == 'K':
      #######################
      # K CLUSTER EXECUTION #
      #######################
      # Create file bg.sh
      bg_lines = ['#!/bin/sh \n',
                  'export HOME=\".\" \n',
                  'export PATH=\"/opt/klocal/Python-2.7/bin:../bin:../gsl-2.1.install/bin:${PATH}\" \n',
                  'export LD_LIBRARY_PATH=\"/opt/klocal/Python-2.7/lib:/opt/klocal/cblas/lib:/opt/local/Python-2.7.3/lib:../lib:../gsl-2.1.install/lib:${LD_LIBRARY_PATH}\" \n',
                  'export NEST_DATA_DIR=\"../share/nest\" \n',
                  'export PYTHONPATH=\"../lib/python2.7/site-packages\" \n',
                  '. ../bin/nest_vars.sh \n',
                  'mkdir ./log \n',
                  'python '+params['whichTest']+'.py \n',
                  ]
      script = open('bg.sh','w')
      script.writelines(bg_lines)
      script.close()
      pjmOptions = ['#!/bin/bash -x \n',
                    '#PJM -m b \n',
                    '#PJM -m e \n',
                    '#PJM --rsc-list \"rscgrp=small\" \n',
                    '#PJM --rsc-list \"node='+params['nbnodes']+'\" \n',
                    '#PJM --rsc-list \"elapse=23:50:00\" \n',
                    '#PJM --mpi \"proc='+params['nbnodes']+'\" \n',
                    '#PJM -s \n',
                    '#PJM --stg-transfiles all \n',
                    '#PJM --mpi \"use-rankdir\" \n',
                    '#PJM --stgin \"rank=* ./*.py %r:./\" \n',
                    '#PJM --stgin \"rank=* ./bg.sh %r:./\" \n',
                    '#PJM --stgin \"rank=* ./*.csv %r:./\" \n',
                    '#PJM --stgin-dir \"rank=0 ../../nest-2.12.0-install-gsl/bin 0:../bin recursive=7\" \n',
                    '#PJM --stgin-dir \"rank=0 ../../nest-2.12.0-install-gsl/lib 0:../lib recursive=7\" \n',
                    '#PJM --stgin-dir \"rank=0 ../../nest-2.12.0-install-gsl/share 0:../share recursive=7\" \n',
                    '#PJM --stgin \"rank=0 ../../gsl.tgz 0:../\" \n',
                    '#PJM --stgout \"rank=* %r:./log/* ./log/ stgout=all\" \n\n',
                    '. /work/system/Env_base \n',
                    'export FLIB_FASTOMP=FALSE \n',
                    'tar -zxf ../gsl.tgz -C ../ \n',
                    'rm -f ../gsl.tgz \n',
                    'mpirun -np '+params['nbnodes']+' sh bg.sh \n',
                    'echo \"finish\"',
                    #'mpiexec -n 2 sh bg.sh \n',
                    #'mpiexec sh bg.sh \n'
                    # 'wait \n'
                    ]
      # write the script file
      print 'Write PJM script file'
      script = open('my_job.sh','w')
      script.writelines(header)
      script.writelines(pjmOptions)
      script.close()
      # execute the script file
      command = 'pjsub ./my_job.sh'
    # starting/queuing the simulation
    print('Executing: '+ command)
    os.system(command)
    print('done.')
    os.chdir('..')

  def recParamExplo(self, pdict):
    # Performs the recursive exploration of parameters values
    try:
      # get the first index of list item (fails with error)
      idx = [isinstance(pdict[entry], list) for entry in pdict].index(True)
      # iterate through the array values
      paramK = pdict.keys()[idx]
      calldict = pdict.copy()
      del calldict[paramK]
      for v in pdict[paramK]:
        calldict[paramK]=v
        self.recParamExplo(calldict)
    except:
      self.launchOneParameterizedRun(self.sim_counter, pdict)
      self.sim_counter += 1

  def expandValues(self):
    # Sugar to get automagically the number of CPUs when nbcpu = -1
    if self.params['nbcpu'] < 0:
      self.params['nbcpu'] = multiprocessing.cpu_count()

  def dispatch(self):
    # Loads the configurations and launch the runs
    self.load_base_config()
    if self.cmd_args.custom != None:
      self.load_custom_config(self.cmd_args.custom)
    self.load_cmdline_config(self.cmd_args)
    self.expandValues()
    self.recParamExplo(self.params)



def main():
    # Parse the commandline arguments
    parser = argparse.ArgumentParser(description="Simulation Dispatcher. Argument precedence: Hardcoded default values < Custom initialization file values < commandline-supplied values.", formatter_class=lambda prog: argparse.HelpFormatter(prog,max_help_position=27))
    parser._action_groups.pop()
    RequiredNamed = parser.add_argument_group('mandatory arguments')
    RequiredNamed.add_argument('--platform', type=str, help='Run the experiment on which platform?', required=True, choices=['Local', 'Sango', 'K'])
    Optional = parser.add_argument_group('optional arguments')
    Optional.add_argument('--custom', type=str, help='Provide a custom file to initialize parameters - without the .py extension', default=None)
    Optional.add_argument('--LG14modelID', type=int, help='Which LG14 parameterization to use?', default=None)
    Optional.add_argument('--whichTest', type=str, help='Which test to run?', choices=['testFullBG', 'testChannelBG'], default=None)
    Optional.add_argument('--nbcpu', type=int, help='Number of CPU to use (-1 to guess)', default=None)
    Optional.add_argument('--nbCh', type=int, help='Number of Basal Ganglia channels to simulate', default=None)
    Optional.add_argument('--interactive', action="store_true", help='Set to enable the display of debug plots', default=False)
    Optional.add_argument('--email', type=str, help='To receive emails when Sango cluster simulations are done', default=None)
    
    cmd_args = parser.parse_args()
    
    dispatcher = JobDispatcher(cmd_args)

    dispatcher.dispatch()

if __name__ == '__main__':
    main()


