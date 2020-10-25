#!/usr/bin/env python3
import boto3
import botocore
from botocore.exceptions import ClientError
import base64
import hashlib
import os.path
import json
import dateutil.parser as dp
import datetime
import click
import re
import logging 
import os
import sys
import pprint
import pathlib

logging.basicConfig(format='%(asctime)s:%(levelname)s:%(message)s', datefmt='%Y:%m:%d-%H:%M:%S')
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def add_options(options):
    """decoration to add a set of options to a function based on a passed list rather than explicitly """
    def _add_options(func):
        for option in reversed(options):
            func = option(func)
        return func

    return _add_options


MAX_NUM_THROTTLE_RETRIES = 16

class ssmManager():

    container_2_image = { "docserver": 'doc',
                          "frontend" : 'frontend',
                          "dbloader" : 'dbloader',
                          "affordability": 'affordability',
                          "scorecard": 'scorecard',
                          "pvm" : 'pvm'
                        }

    def __init__(self, session, log, build_env=None):
        self.log = log
        my_retry_config = botocore.config.Config(retries={'max_attempts': MAX_NUM_THROTTLE_RETRIES})
        self.ssm = boto3.client('ssm', config=my_retry_config)

        self.OutRe = re.compile(r'(.*)\n', re.MULTILINE)

        if (build_env is not None):
            self.setBuildEnv(build_env)

        # ssm configs
        self.ssmDryrun = False
        self.ssmKeyId = None
        self.ssmOverwrite = False

    def setBuildEnv(self, build_env):
        self.build_env = build_env
        self.asgRe = re.compile(r'^{}'.format(self.build_env))

    def __toDHMS(self, seconds, return_type='list'):
        """Utility function to convert seconds to days, hours, minutes and seconds """
        remainder = int(seconds)
        days  = divmod(remainder, 86400)[0]
        remainder = remainder - (86400 * days)

        hours  = divmod(remainder, 3600)[0]
        remainder = remainder - (3600 * hours)

        minutes  = divmod(remainder, 60)[0]
        seconds = remainder - (60 * minutes)

        if return_type == 'string':
            return "{:02d}-{:02d}:{:02d}:{:02d}".format(days, hours, minutes, seconds)

        return([days, hours, minutes, seconds])

    def ssmGetValueFromFile(self,path):
        with open(path, "r") as fp:
            value = fp.read().rstrip('\n')
        return(value)

    def ssmUploadParameters(self, path=None):
        if len(path) == 0:
            path=None
        if (self.ssmRoot is None):
            self.log.error("ssmRoot is not set")
            return False
        if (self.ssmRoot == '/'):
            self.log.error("ssmRoot cannot be '/'")
            return False
        if path is None:
            path = list('/')

        if (self.ssmKeyId is None):
            if 'KEY_ID' not in os.environ:
                self.log.error("Missing key_id, use --key_id or KEY_ID in the environment")
                return
            else:
                self.ssmKeyId=os.environ['KEY_ID']

        ssmReList=list()
        for p in path:
            ssmReList.append(re.compile('^'+p))

        ssmPathRe = re.compile(r'^'+self.ssmRoot+'(.*)$')

        for dirName, subdirList, fileList in os.walk(self.ssmRoot):                    

            match = ssmPathRe.match(dirName)

            # this should always match
            if not match:
                continue

            ssmPathCandidate = match.group(1)

            for fname in fileList:
                ssmFullPath = ssmPathCandidate+"/"+fname
                for reg in ssmReList:
                    ssmMatch = reg.match(ssmFullPath)
                    if ssmMatch:
                        value = self.ssmGetValueFromFile(dirName+"/"+fname)
                        if ( self.ssmDryrun ):
                            print("Upload: "+dirName+"/"+fname+" to "+ssmFullPath)
                            print("value: " + value )
                        else:
                            try:
                                self.ssm.put_parameter(Name=ssmFullPath, 
                                                       Value=value,
                                                       Overwrite=self.ssmOverwrite,
                                                       Type='SecureString',
                                                       KeyId=self.ssmKeyId)
                                self.log.info("Uploaded {}".format(ssmFullPath))
                            except ClientError as exc:
                                code = exc.response['Error']['Code']
                                self.log.error("Upload parameter failed for '{}', error ({})".format(ssmFullPath, code))


    def ssmStoreParameterLocal(self, name, value):
        if (self.ssmRoot is None):
            self.log.error("ssmRoot is not set")
            return False
        if (self.ssmRoot == '/'):
            self.log.error("ssmRoot cannot be '/'")
            return False
        dirname = os.path.dirname(name)
        filename = os.path.basename(name)
        if (os.path.exists(dirname)):
            if (os.path.isfile(dirname)):
                self.log.error("Cannot represent parameter '{}' as path '{}' is a file".format(name,dirname))
                return False
        else:
            try:
                pathlib.Path(self.ssmRoot+dirname).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self.log.error("mkdir got exception '{}' for {}".format(e, name))
                return False
        
        self.log.info("Saving "+self.ssmRoot+name)
        try:
            with open(self.ssmRoot+"/./"+name,"w") as fd:
                fd.write(value+"\n")
        except Exception as e:
            self.log.error("Got error '{}' writing to path '{}'".format(e, name))
            return False

        return True


    def getParameter(self, Name, callBack = None):
        try:
            response = self.ssm.get_parameter(Name=Name, WithDecryption=True)
            if (callBack is None):
                print(response['Parameter']['Value'])
            else:
                callBack(response['Parameter']['Value'])
        except ClientError as exc:
            code = exc.response['Error']['Code']
            self.log.error("Got error ({}) when attempting to retrieve parameter '{}'".format(code, Name))


    def getParameters(self, path, justList=False, callBack=None):
        nextToken = ' '
        start = True
        while(start or nextToken != ' '):
            start = False
            try:
                responses = self.ssm.get_parameters_by_path(Path=path, WithDecryption=True, Recursive=True, NextToken=nextToken)
                nextToken = responses['NextToken'] if 'NextToken' in responses else ' '
                for response in responses['Parameters']:
                    if justList:
                        print(response['Name'])
                    else:
                        if self.ssmDryrun is True or callBack is None:
                            print('{}	{}'.format(
                                response['Name'],
                                response['Value']))
                        else:
                            callBack(response['Name'], response['Value'])
            except ClientError as exc:
                code = exc.response['Error']['Code']
                self.log.error("Got error ({}) when attempting to retrieve parameters on path '{}'".format(code, path))

    def ssmDeleteParameter(self, name, value):
        if self.ssmDryrun:
            self.log.info("Would delete parameter {} of value {}".format(name ,value))
        try:
            self.ssm.delete_parameter(Name=name)
            self.log.info("Delete parameter '{}', value was ({})".format(name, value))
        except ClientError as exc:
            code = exc.response['Error']['Code']
            self.log.error("Got error ({}) when attempting to delete parameter '{}'".format(code, name))


    def listParameterData(self, fltr=None):
        if fltr is None:
            PF = [{ 'Key': 'Name', 'Option': 'BeginsWith', 'Values': ['/']}]
        else:
            PF = [{ 'Key': 'Name', 'Option': 'BeginsWith', 'Values': fltr}]
        nextToken = ' '
        start = True
        while(start or nextToken != ' '):
            start = False
            response = self.ssm.describe_parameters(MaxResults=50, 
                                                    NextToken=nextToken,
                                                    ParameterFilters=PF)
            nextToken = response['NextToken'] if 'NextToken' in response else ' '
            for params in response['Parameters']:
                print(" {}".format(params['Name']))

global_options = [
    click.option('--build_env', required=True, type=click.STRING, help="Environment (stage/prod/pre-prod...)"),
]

ssm_options = [ 
    click.argument('paths', type=click.STRING, nargs=-1),
    click.option('--get', is_flag=True, default=False, help="Retrieve the parameters value"),
    click.option('--path', is_flag=True, default=False, help="Retrieve the parameters from the provided paths"),
    click.option('--savepath', required=False, type=click.STRING, help="Local path to which to save parameter files, only valid with --path"),
    click.option('--uploadpath', required=False, type=click.STRING, help="Local path to which to load parameter files"),
    click.option('--dryrun', is_flag=True, default=False, help="Say what you would have done, don't do anything"),
    click.option('--key_id', required=False, default=None, type=click.STRING, help="Key Id for encrypting uploaded parameters, will source from environment KEY_ID if not set"),
    click.option('--force', is_flag=True, default=False, help="Overwrite existing parameters when uploading"),
    click.option('--delete', is_flag=True, default=False, help="delete the specified parameters set with --path - use with care, suggest --dryrun first"),
    ]
@click.command(name='ssm', short_help='Parameter functions')
@add_options(ssm_options)
def ssm(delete, force, key_id, dryrun, uploadpath, savepath, path, get, paths):
    global em
    em.ssmDryrun = dryrun
    em.ssmKeyId = key_id
    em.ssmOverwrite = force
    callBack = None

    # if --upload we use the beginwith pathlist
    if uploadpath is not None:
        em.ssmRoot=uploadpath
        em.ssmUploadParameters(list(paths))
        return

    # --delete turns on the delete callback
    # needs --path
    if delete:
        callBack = em.ssmDeleteParameter

    # savepath turns on store callback
    # need --path
    if savepath is not None:
        em.ssmRoot=savepath
        callBack = em.ssmStoreParameterLocal

    # if --path is set we do the action on the callback
    if path:
        for pth in paths:
            em.getParameters(pth, callBack=callBack)
        return

    # --get just gets a single parameter
    if get:
        for name in paths:
            em.getParameter(name)
        return

    # if nothing else then we just list the parameters matching begins with
    for name in paths:
            em.getParameters(name,justList=True)

@click.group()
def cli():
    global em
    session = boto3.Session()
    em = ssmManager(session=session, log=logger)

cli.add_command(ssm)

if __name__ == '__main__':
    cli()

