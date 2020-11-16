# ssmParameterManager
A python based system for managing large numbers of ssm parameters store entries.

The system is designed so that the user can pull large numbers of parameters by path into a local directory, edit and manipulate them and then upload them.

## Note 1: 

This system, as of current functionallity does not work with paths that are 'directories' and 'files' as is perfectly reasonable with ssm parameter store because it is a object based storage system

for example, if both of these paths have a value associated with them, the manager won't work correctly.

```
/this/that
/this/that/the/other
```
This is because 'that' has to be a directory and a file at the same time.

## Note 2:

The utility assumes that you will be encrypting parameters. So you either have to supply the key id on the command line or set it thus:
```
$ export KEY_ID=xxxxxxxx-xxxx-xxxx-xxxxx-xxxxxxxxxxxx
```

Change to suit the key you wish to use.


## Command line operation
```
Usage: param.py [OPTIONS] [PATHS]...

Options:
  --get              Retrieve the parameters value
  --path             Retrieve the parameters from the provided paths
  --savepath TEXT    Local path to which to save parameter files, only valid
                     with --path

  --uploadpath TEXT  Local path to which to load parameter files
  --dryrun           Say what you would have done, don't do anything
  --key_id TEXT      Key Id for encrypting uploaded parameters, will source
                     from environment KEY_ID if not set

  --force            Overwrite existing parameters when uploading
  --delete           delete the specified parameters set with --path - use
                     with care, suggest --dryrun first

  --help             Show this message and exit.
```
  
### Examples
 
 All these examples assume that you have KEY_ID set in your environment.
 
To recursive list parameters 'under' a path.
 
 ```
 param.py /some/path
 ```
 
To list a number of paths
 
 ```
 param.py /some/path /someother/path
 ```
 
To get just a single value to stdout:
 
 ```
 param.py --get /some/parameter/path
 ```
 
To download everything into a local directory called ALL
 
 ```
 param.py --savepath ./ALL --path /
 ```

To download some specific paths in a directory called 'mystuff'

```
param.py --savepath ./mystuff --path /local/shared /stage/lime
```

To upload parameters in mystuff, by uploading everyting under ./mystuff/martin as /martin.
 
```
param.py --uploadpath ./mystuff --path /martin
``` 

Do a dryrun of deleting everthing below /martin. Do not forget the --path, otherwise the --delete will be ignored and it will just list parameters.

```
param.py --delete --dryrun --path /martin
``` 
 
Actually delete everthing below /martin, again don't forget --path, other it will just do the list action. When the delete is working it will log each parameter deleted with its current value.

```
param.py --delete --path /martin
``` 
