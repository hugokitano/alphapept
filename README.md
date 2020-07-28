# AlphaPept
> A modular, python-based framework for mass spectrometry. Powered by nbdev. Supercharged with numba.


![alphapept](nbs\images\alphapept_logo.png)

## Current ToDo here:

- Compile Standalone Installer / Gui and update Installation Instructions
- Write brief introduction on how to use the modules
- Write how to report bugs / contribute


## Documentation

The documentation is automatically build based the jupyter notebooks and can be found [here](https://mannlabs.github.io/alphapept/):

## Installation Instructions

### Windows Installer

ToDo: Here you will find a link to a windows installer for installation.

### Conda
It is strongly recommended to install AlphaPept in its own environment.
1. Open the console and create a new conda environment: conda create --name alphapept python
2. Activate the environment: `source activate alphapept` for Linux / Mac Os X or `activate alphapept` for Windows
2. Redirect to the folder of choice and clone the repository: `git clone https://github.com/MannLabs/alphapept.git`
3. Install the package with `python setup.py install`

    Note: If you would like to use alphapept in your jupyter notebook environment, additionally install nb_conda: `conda install nb_conda`

If AlphaPept is installed correctly, you should be able to import Alphapept as a package within the environment, see below.

## How to use
You can use AlphaPept via the command line or via the GUI.

### Standalone installation

Simply click the shortcut for the GUI or the command line.

### Python Package

To launch the command line interface use:
`python -m alphapept`

This allows to select the different modules. To start the GUI use:
`python -m alphapept gui`

Likewise, to start the watcher use:
`python -m alphapept watcher`

Once AlphaPept is correctly installed you can use it like any other python module.

```
from alphapept.fasta import get_frag_dict, parse
from alphapept import constants

peptide = 'PEPT'

get_frag_dict(parse(peptide), constants.mass_dict)
```




    {'b1': 98.06004032687,
     'b2': 227.10263342686997,
     'b3': 324.15539728686997,
     'y1': 120.06551965033,
     'y2': 217.11828351033,
     'y3': 346.16087661033}



## Notes for Programmers

### Literal Programming
A key feature is the use of [nbdev](https://github.com/fastai/nbdev). We like to keep the entrance barrier low to attract new coders to contribute to the AlphaPept package. For this, we see nbedv as an ideal tool to document and modify code.

### Testing

In order to make AlphaPept a sustainable package, it is imperative that all functions have tests. This is not only to ensure the proper execution of the function but also for the long run when wanting to keep up-to-date with package updates. For tracking package updates, we rely on [dependabot](https://dependabot.com). For continuous integration, we use GitHub Actions.

### Numba - first

We heavily rely on the [Numba](http://numba.pydata.org) package for efficient computation. As writing classes in numba with `@jitclass` requires type specification, in most cases, we prefer functional programming over
Object-oriented programming for simplicity. Here, adding the decorator `@njit` is mostly enough.

### Parallelization strategies

Python has some powerful parallelization tools, such as the `multiprocessing` library. `Numba` allows loops to be executed in parallel when flagging with `prange`, which is, from a syntactic point of view, a very elegant solution to parallel processing. It comes with the downside that we cannot easily track the progress of parallel functions that use `prange`. We, therefore, chunk data where possible to be able to have a progress bar. Additionally, currently, it is not possible to set the number of cores that should be used.

From a data analysis point of view, there are several considerations to be taken into account: When processing multiple files in parallel, it would be suitable to launch several processes in parallel, where the multiprocessing library would come in handy. On the other hand, when only wanting to investigate a single file, having the individual functions parallelized would be beneficial.

Hence, the core idea is to write fast single-core functions and also have parallelized versions where applicable. For multi-file processing, we will rely on the `multiprocessing`.

### Callbacks

As AlphaPept is intended to be the backend of a tool with GUI, we ideally want to be able to get a progress bar out of the major functions. For this, we can pass a `callback`-argument to the major functions. If the argument is passed, it will return the current progress in the range from 0 to 1.

### Constants 

One good way to handle constants would be to use globals. However, numba is not able to use typed dictionaries/classes as globals. We therefore pass them as variables (such as the mass_dict), which in some cases leads to functions with a lot of arguments. Note that `numba` is not able to handle `kwargs` and `args` at this point.


### Version bumping

We are using the python package [`bump2version`](https://github.com/c4urself/bump2version). You can use this to bump the version number. Currently specified is: `bump2version`: (`major`, `minor`, `patch`):

* e.g.: `bump2version patch` for a patch
