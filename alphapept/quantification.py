# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/08_quantification.ipynb (unless otherwise specified).

__all__ = ['gaussian', 'return_elution_profile', 'simulate_sample_profiles', 'get_total_error',
           'normalize_experiment_SLSQP', 'normalize_experiment_BFGS', 'delayed_normalization', 'generate_dummy_data',
           'get_protein_ratios', 'triangle_error', 'solve_profile', 'protein_profile', 'protein_profile_parallel',
           'protein_profile_parallel_ap', 'protein_profile_parallel_mq']

# Cell
import random
import numpy as np
import logging

def gaussian(mu: float, sigma: float, grid : np.ndarray) -> np.ndarray:
    """Calculates normally distributed probability densities along an input array.

    Args:
        mu (float): mean of ND.
        sigma (float): standard deviation of ND.
        grid (np.ndarray): input array np.int[:]. For each element of the array, the  probability density is calculated.

    Returns:
        np.ndarray: probability density array, np.float[:].
    """
    norm = 0.3989422804014327 / sigma
    return norm * np.exp(-0.5 * ((grid - mu) / sigma) ** 2)

# Cell
def return_elution_profile(timepoint: float, sigma : float, n_runs : int) -> np.ndarray:
    """Simulates a gaussian elution profile.

    Args:
        timepoint (float): coordinate of the peak apex.
        sigma (float): standard deviation of the gaussian.
        n_runs (int): number of points along which the density is calculated.

    Returns:
        np.ndarray: probability density array, np.float[:].
    """
    return gaussian(timepoint, sigma, np.arange(0, n_runs))

# Cell
def simulate_sample_profiles(n_peptides: int, n_runs: int, n_samples: int, threshold:float=0.2, use_noise:bool=True) -> [np.ndarray, np.ndarray]:
    """Generates random profiles to serve as test_data.

    Args:
        n_peptides (int): number of peptides to be simulated.
        n_runs (int): number of runs to be simulated.
        n_samples (int): number of samples to be simulated.
        threshold (float, optional): threshold below which a simulated intensity will be discarded. Defaults to 0.2.
        use_noise (bool, optional): add simulated noise to the profile values. Defaults to True.

    Returns:
        Tuple[np.ndarray, np.ndarray]: profiles: np.float[:,:,:] array containing the simulated profiles, true_normalization: np.float[:,:,:] array containing the ground truth.
    """
    np.random.seed(42)
    abundances = np.random.rand(n_peptides)*10e7

    true_normalization = np.random.normal(loc=1, scale=0.1, size=(n_runs, n_samples))
    true_normalization[true_normalization<0] = 0
    true_normalization = true_normalization/np.max(true_normalization)
    maxvals = np.max(true_normalization, axis=1)
    elution_timepoints = random.choices(list(range(n_runs)), k=n_peptides)

    profiles = np.empty((n_runs, n_samples, n_peptides))
    profiles[:] = np.nan

    for i in range(n_peptides):

        elution_timepoint = elution_timepoints[i]
        abundance = abundances[i]

        profile = return_elution_profile(elution_timepoint, 1, n_runs)
        profile = profile/np.max(profile)
        profile = profile * abundance
        elution_profiles = np.tile(profile, (n_samples, 1)).T

        # Add Gaussian Noise
        if use_noise:
            noise = np.random.normal(1, 0.2, elution_profiles.shape)
            noisy_profile = noise * elution_profiles
        else:
            noisy_profile = elution_profiles

        normalized_profile = noisy_profile * true_normalization

        normalized_profile[normalized_profile < threshold] = 0
        normalized_profile[normalized_profile == 0] = np.nan


        profiles[:,:,i] = normalized_profile

    return profiles, true_normalization

# Cell
def get_total_error(normalization: np.ndarray, profiles: np.ndarray) -> float:
    """Computes the summed peptide errors over the whole dataset.

    Args:
        normalization (np.ndarray): per sample normalization factors.
        profiles (np.ndarray): peptide intensity profiles over the dataset.

    Returns:
        float: summed peptide error.
    """
    normalization = normalization.reshape(profiles.shape[:2])

    reshaped_profiles = np.transpose(profiles, (2, 0, 1)) # move axes to support broadcasting
    normalized_profiles = reshaped_profiles*normalization
    pep_ints_all = np.nansum(normalized_profiles, axis=1)

    #returns upper triangular indices, with offset of 1, which gives us every pair of indices in our array
    i, j = np.triu_indices(pep_ints_all.shape[1], k=1) #returns upper triangular indices
    x = pep_ints_all[:,i]
    y = pep_ints_all[:,j]

    #this operation will result in pos/neg infinity for zero values in x or y, and will cause expected runtime warnings
    errors = np.log(x/y)

    #change pos/neg infinity values to 0 to compute accurate sum
    errors = np.nan_to_num(errors, posinf=0, neginf=0)

    #absolute value is not necessary as squaring should always result in a non negative value
    total_error = (errors**2).sum()
    return total_error

# Cell
from scipy.optimize import minimize
import pandas as pd
import numpy as np
import warnings

def normalize_experiment_SLSQP(profiles: np.ndarray) -> np.ndarray:
    """Calculates normalization with SLSQP approach.

    Args:
        profiles (np.ndarray): peptide intensities.

    Returns:
        np.ndarray: normalization factors.
    """
    x0 = np.ones(profiles.shape[0] * profiles.shape[1])
    bounds = [(0.1, 1) for _ in x0]
    res = minimize(get_total_error, args = profiles , x0 = x0*0.5, bounds=bounds, method='SLSQP', options={'disp': False, 'maxiter':100*profiles.shape[1]})

    solution = res.x/np.max(res.x)
    solution = solution.reshape(profiles.shape[:2])

    return solution

# Cell
def normalize_experiment_BFGS(profiles: np.ndarray) -> np.ndarray:
    """Calculates normalization with BFGS approach.

    Args:
        profiles (np.ndarray): peptide intensities.

    Returns:
        np.ndarray: normalization factors.
    """
    x0 = np.ones(profiles.shape[0] * profiles.shape[1])
    bounds = [(0.1, 1) for _ in x0]
    res = minimize(get_total_error, args = profiles , x0 = x0*0.5, bounds=bounds, method='L-BFGS-B', options={'disp': False, 'maxiter':100*profiles.shape[1]} )

    solution = res.x/np.max(res.x)
    solution = solution.reshape(profiles.shape[:2])

    return solution

# Cell
def delayed_normalization(df: pd.DataFrame, field: str='ms1_int_sum', minimum_occurence:bool=None) -> [pd.DataFrame, np.ndarray]:
    """Returns normalization factors for given peptide intensities.
    If the solver does not converge, the unnormalized data will be used.

    Args:
        df (pd.DataFrame): alphapept quantified features table.
        field (str, optional): The column in df containing the quantitative peptide information (i.e. precursor intensities).
        minimum_occurence (bool, optional): minimum number of replicates the peptide must be observed in. Defaults to None.

    Returns:
        [pd.DataFrame, np.ndarray]: pd.DataFrame: alphapept quantified features table extended with the normalized intensities, np.ndarray: normalized intensities
    """
    samples = np.sort(df['sample_group'].unique()).tolist()
    n_samples = len(samples)

    fractions = np.sort(df['fraction'].unique()).tolist()

    n_fractions = len(fractions)

    df_max = df.groupby(['precursor','fraction','sample_group'])[field].max() #Maximum per fraction

    prec_count = df_max.index.get_level_values('precursor').value_counts()

    if not minimum_occurence:
        minimum_occurence = np.percentile(prec_count[prec_count>1].values, 75) #Take the 25% best datapoints
        logging.info('Setting minimum occurence to {}'.format(minimum_occurence))

    shared_precs = prec_count[prec_count >= minimum_occurence]


    precs = shared_precs.index.tolist()
    n_profiles = len(precs)

    selected_precs = df_max.loc[precs]
    selected_precs = selected_precs.reset_index()

    profiles = np.empty((n_fractions, n_samples, n_profiles))
    profiles[:] = np.nan

    #get dictionaries
    experiment_dict = {_:i for i,_ in enumerate(fractions)}
    samples_dict = {_:i for i,_ in enumerate(samples)}
    precursor_dict = {_:i for i,_ in enumerate(precs)}

    prec_id = [precursor_dict[_] for _ in selected_precs['precursor']]
    frac_id = [experiment_dict[_] for _ in selected_precs['fraction']]
    file_id = [samples_dict[_] for _ in selected_precs['sample_group']]

    profiles[frac_id,file_id, prec_id] = selected_precs[field]


    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        logging.info(f'Delayed normalization with SLSQP on {profiles.shape}')

        try:
            normalization = normalize_experiment_SLSQP(profiles)
            norm1d = np.ravel(normalization)
            if sum((norm1d!=1))==0:
                raise ValueError("optimization with SLSQP terminated at initial values. Trying BFGS")
        except ValueError: # SLSQP error in scipy https://github.com/scipy/scipy/issues/11403
            logging.info('Normalization with SLSQP failed. Trying BFGS')
            normalization = normalize_experiment_BFGS(profiles)
            norm1d = np.ravel(normalization)
            if sum((norm1d!=1))==0:
                logging.warn('No normalization factors could be determined. Continuing with non-normalized data.')


    #intensity normalization: total intensity to remain unchanged

    df[field+'_dn'] = df[field]*normalization[[experiment_dict[_] for _ in df['fraction']], [samples_dict[_] for _ in df['sample_group']]]
    df[field+'_dn'] *= df[field].sum()/df[field+'_dn'].sum()

    return df, normalization

# Cell
import numpy as np
import string
from time import time
import pandas as pd

np.random.seed(42)

def generate_dummy_data(n_sequences: int, n_samples: int, noise:bool=True, remove:bool= True, peptide_ratio:bool= True, abundance:bool=True, signal_level:int=100, noise_divider:int=10, keep:float=0.8) -> [pd.DataFrame, list, np.ndarray]:
    """Simulate an input dataset of peptide intensities.

    Args:
        n_sequences (int): number of peptides to simulate.
        n_samples (int): number of samples to simulate.
        noise (bool, optional): add random signal to distort the simulated intensity levels. Defaults to True.
        remove (bool, optional): remove intensities (i.e. add missing values). Defaults to True.
        peptide_ratio (bool, optional): simulate different peptide intensities. Defaults to True.
        abundance (bool, optional): simulate different abundances for each sample (i.e. systematic shifts). Defaults to True.
        signal_level (int, optional): signal level for simulated intensity. Defaults to 100.
        noise_divider (int, optional): the factor through which the noise is divided (higher factor -> higher signal to noise). Defaults to 10.
        keep (float, optional): aimed-at fraction of non-missing values, applies if 'remove' is set. Defaults to 0.8.

    Returns:
        [pd.DataFrame, list, np.ndarray]: pd.DataFrame: simulated dataset with peptide intensities, list: sample names: np.ndarray: shift factors of each sample
    """
    species = ['P'+str(_) for _ in range(1,n_sequences+1)]
    sample = [string.ascii_uppercase[_%26]+str(_//26) for _ in range(n_samples)]

    if peptide_ratio:
        peptide_ratio = np.random.rand(n_sequences)
        peptide_ratio = peptide_ratio/np.sum(peptide_ratio)
    else:
        peptide_ratio = np.ones(n_sequences)

    if abundance:
        abundance_profile = np.random.rand(n_samples,1)
    else:
        abundance_profile = np.ones((n_samples,1))

    original_signal = np.ones((n_samples, n_sequences))

    noise_sim = (np.random.rand(n_samples, n_sequences)-0.5)/noise_divider

    if noise:
        noisy_signal = original_signal+noise_sim
        noisy_signal = noisy_signal*signal_level*peptide_ratio*abundance_profile
    else:
        noisy_signal = original_signal*signal_level*peptide_ratio*abundance_profile

    if remove:
        #Remove points
        keep_probability = keep #keep 60% of the points
        to_remove = np.random.rand(n_samples, n_sequences)
        to_remove = to_remove>=keep_probability

        dummy_data = noisy_signal.copy()

        dummy_data[to_remove] = 0

    else:
        dummy_data = noisy_signal


    dummy_data = pd.DataFrame(dummy_data, index = sample, columns = species).T

    ground_truth = abundance_profile.flatten()
    ground_truth = ground_truth/np.max(ground_truth)

    return dummy_data, sample, ground_truth

# Cell
from numba import njit

@njit
def get_protein_ratios(signal: np.ndarray, column_combinations: list, minimum_ratios:int = 1) -> np.ndarray:
    """Calculates the protein ratios between samples for one protein.

    Args:
        signal (np.ndarray): np.array[:,:] containing peptide intensities for each sample.
        column_combinations (list): list of all index combinations to compare (usually all sample combinations).
        minimum_ratios (int, optional): minimum number of peptide ratios necessary to calculate a protein ratio. Defaults to 1.

    Returns:
        np.ndarray: np.array[:,:] matrix comparing the ratios for all column combinations.
    """
    n_samples = signal.shape[1]
    ratios = np.empty((n_samples, n_samples))
    ratios[:] = np.nan

    for element in column_combinations:
        i = element[0]
        j = element[1]

        ratio = signal[:,j] / signal[:,i]

        non_nan = np.sum(~np.isnan(ratio))

        if non_nan >= minimum_ratios:
            ratio_median = np.nanmedian(ratio)
        else:
            ratio_median = np.nan

        ratios[j,i] = ratio_median

    return ratios

# Cell
@njit
def triangle_error(normalization: np.ndarray, ratios:np.ndarray) -> float:
    """Calculates the difference between calculated ratios and expected ratios.

    Args:
        normalization (np.ndarray): Used normalization.
        ratios (np.ndarray): Peptide ratios.

    Returns:
        float: summed quadratic difference.
    """
    int_matrix = np.repeat(normalization, len(normalization)).reshape((len(normalization), len(normalization))).transpose()
    x = (np.log(ratios) - np.log(int_matrix.T) + np.log(int_matrix))**2

    return np.nansum(x)

# Cell
## L-BFGS-B
from scipy.optimize import minimize, least_squares

def solve_profile(ratios: np.ndarray, method: str) -> [np.ndarray, bool]:
    """Calculates protein pseudointensities with a specified solver.
    Args:
        ratios (np.ndarray): np.array[:,:] matrix containing all estimated protein ratios between samples.
        method (str): string specifying which solver to use.
    Raises:
        NotImplementedError: if the solver is not implemented.
    Returns:
        [np.ndarray, bool]: np.ndarray: the protein pseudointensities, bool: wether the solver was successful.
    """
    if method not in ['L-BFGS-B', 'SLSQP', 'Powell', 'trust-constr','trf']:
        raise NotImplementedError(method)

    x0 = np.ones(ratios.shape[1])
    bounds = [(min(np.nanmin(ratios), 1/np.nanmax(ratios)), 1) for _ in x0]

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=RuntimeWarning)

        if method == 'trf':
            bounds = (x0*0+0.01, x0)
            res_wrapped = least_squares(triangle_error, args = [ratios] , x0 = x0, bounds=bounds, verbose=0, method = 'trf')
            solution = res_wrapped.x
        else:

            ncor = max((20, int(2*np.ceil(np.sqrt(ratios.shape[0])))))

            res_wrapped = minimize(triangle_error, args = ratios , x0 = x0, bounds=bounds, method = method, options={'maxiter':int(1e6),'maxfun':int(ratios.shape[0]*2e4), 'eps': 1e-06, 'maxcor':ncor}, )
            solution = res_wrapped.x

    solution = solution/np.max(solution)

    return solution, res_wrapped.success

# Cell
from numba.typed import List
from itertools import combinations
import pandas as pd


def protein_profile(files: list, minimum_ratios: int, chunk:tuple) -> (np.ndarray, np.ndarray, str):
    """Function to extract optimal protein ratios for a given input of peptides.

    Note for the chunk argument: This construction is needed to call this function from a parallel pool.

    Args:
        files (list): A list of files for which the profile shall be extracted.
        minimum_ratios (int): A minimum number of peptide ratios to be considered for optimization.
        chunk: (tuple[pd.DataFrame, str]): A pandas dataframe with the peptide information and a string to identify the protein.

    Returns:
        np.ndarray: optimized profile
        np.ndarray: profile w/o optimization
        str: protein identifier
    """
    grouped, protein = chunk

    files_ = grouped.index.get_level_values('sample_group').unique().tolist()

    selection = grouped.unstack().T.copy()
    selection = selection.replace(0, np.nan)

    if len(files_) > 1:
        success = False
        column_combinations = List()
        [column_combinations.append(_) for _ in combinations(range(len(files_)), 2)]

        ratios = get_protein_ratios(selection.values, column_combinations, minimum_ratios)

        retry = False
        try:
            solution, success = solve_profile(ratios, 'L-BFGS-B')
        except ValueError:
            retry = True

        if retry or not success:
            logging.info('Normalization with L-BFGS-B failed. Trying Powell')
            solution, success = solve_profile(ratios, 'Powell')

        pre_lfq = selection.sum().values

        if not success or np.sum(~np.isnan(ratios)) == 0: # or np.sum(solution) == len(pre_lfq):
            profile = np.zeros(len(files_))
            if np.sum(np.isnan(ratios)) != ratios.size:
                logging.info(f'Solver failed for protein {protein} despite available ratios:\n {ratios}')

        else:
            invalid = ((np.nansum(ratios, axis=1) == 0) & (np.nansum(ratios, axis=0) == 0))
            peptide_int_sum = pre_lfq.sum() * solution
            peptide_int_sum[invalid] = 0
            profile = peptide_int_sum * pre_lfq.sum() / np.sum(peptide_int_sum) #Normalize inensity again
    else:
        success = True
        pre_lfq = profile = selection.sum(axis=0).values

    #Rewrite ratios
    profile_dict = dict(zip(files_, profile))
    pre_dict = dict(zip(files_, pre_lfq))
    profile = np.array([0 if file not in profile_dict else profile_dict[file] for file in files])
    pre_lfq = np.array([0 if file not in pre_dict else pre_dict[file] for file in files])

    return profile, pre_lfq, protein, success


# Cell

import os
import alphapept.performance
from functools import partial

# This function invokes a parallel pool and has therfore no dedicated test in the notebook
def protein_profile_parallel(df: pd.DataFrame, minimum_ratios: int, field: str, callback=None) -> pd.DataFrame:
    """Derives LFQ intensities from the feature table.

    Args:
        df (pd.DataFrame): Feature table by alphapept.
        minimum_ratios (int): Minimum number of peptide ratios necessary to derive a protein ratio.
        field (str): The field containing the quantitative peptide information (i.e. precursor intensities).
        callback ([type], optional): Callback function. Defaults to None.

    Returns:
        pd.DataFrame: table containing the LFQ intensities of each protein in each sample.
    """
    unique_proteins = df['protein_group'].unique().tolist()

    samples = df['sample_group'].unique().tolist()
    samples.sort()

    columnes_ext = [_+'_LFQ' for _ in samples]
    protein_table = pd.DataFrame(index=unique_proteins, columns=columnes_ext + samples)

    # Used to be max, now sum() (to group fractions)
    grouped = df[[field, 'sample_group','precursor','protein_group']].groupby(['protein_group','sample_group','precursor']).sum()


    results = []

    if len(samples) > 1:
        logging.info('Preparing protein table for parallel processing.')
        split_df = []

        for idx, protein in enumerate(unique_proteins):
            split_df.append((grouped.loc[protein], protein))
            if callback:
                callback((idx+1)/len(unique_proteins)*1/5)

        results = []

        logging.info(f'Starting protein extraction for {len(split_df)} proteins.')
        n_processes = alphapept.performance.set_worker_count(
            worker_count=0,
            set_global=False
        )
        with alphapept.performance.AlphaPool(n_processes) as p:
            max_ = len(split_df)
            for i, _ in enumerate(p.imap_unordered(partial(protein_profile, samples, minimum_ratios), split_df)):
                results.append(_)

                if not _[-1]:
                    logging.info(f'LFQ profile extraction for protein {_[-2]} did not converge. Setting to zero.')
                if callback:
                    callback((i+1)/max_*4/5+1/5)

        for result in results:
            profile, pre_lfq, protein, success = result
            protein_table.loc[protein, [_+'_LFQ' for _ in samples]] = profile
            protein_table.loc[protein, samples] = pre_lfq

        protein_table[protein_table == 0] = np.nan
        protein_table = protein_table.astype('float')
    else:
        protein_table = df.groupby(['protein_group'])[field].sum().to_frame().reset_index()
        protein_table = protein_table.set_index('protein_group')
        protein_table.index.name = None
        protein_table.columns=[samples[0]]

        if callback:
            callback(1)

    return protein_table

# Cell

# This function invokes a parallel pool and has therfore no dedicated test in the notebook
def protein_profile_parallel_ap(settings: dict, df : pd.DataFrame, callback=None) -> pd.DataFrame:
    """Derives protein LFQ intensities from the alphapept quantified feature table

    Args:
        settings (dict): alphapept settings dictionary.
        df (pd.DataFrame): alphapept feature table.
        callback ([type], optional): [description]. Defaults to None.

    Raises:
        ValueError: raised in case of observed negative intensities.

    Returns:
        pd.DataFrame: table containing the LFQ intensities of each protein in each sample.
    """
    minimum_ratios = settings['quantification']['lfq_ratio_min']
    field = settings['quantification']['mode']

    if field+'_dn' in df.columns:
        field_ = field+'_dn'
    else:
        field_ = field

    if df[field_].min() < 0:
        raise ValueError('Negative intensity values present.')

    protein_table = protein_profile_parallel(df, minimum_ratios, field_, callback)

    return protein_table

# This function invokes a parallel pool and has therfore no dedicated test in the notebook
def protein_profile_parallel_mq(evidence_path : str, protein_groups_path: str, minimum_ratios: int = 1, minimum_occurence:bool=None, delayed:bool = True, callback=None) -> pd.DataFrame:
    """Derives protein LFQ intensities from Maxquant quantified features.

    Args:
        evidence_path (str): path to the Maxquant standard output table evidence.txt.
        protein_groups_path (str): path to the Maxquant standard output table proteinGroups.txt.
        minimum_ratios (int): minimum ratios (LFQ parameter)
        minimum_occurence (int): minimum occurence (LFQ parameter)
        delayed (bool): toggle for delayed normalization (on/off)
        callback ([type], optional): [description]. Defaults to None.

    Raises:
        FileNotFoundError: if Maxquant files cannot be found.

    Returns:
        pd.DataFrame: table containing the LFQ intensities of each protein in each sample.
    """
    logging.info('Loading files')

    for file in [evidence_path, protein_groups_path]:
        if not os.path.isfile(file):
            raise FileNotFoundError(f'File {file} not found.')

    evd = pd.read_csv(evidence_path, sep='\t')
    ref = pd.read_csv(protein_groups_path, sep='\t')

    experiments = evd['Experiment'].unique().tolist()
    logging.info(f'A total of {len(experiments):,} files.')


    if 'Fraction' not in evd.keys():
        logging.info('File does not contain Fractions. Setting Fractions to 1')
        evd['Fraction'] = 1

    protein_df = []

    max_ = len(ref)
    for i in range(max_):
        investigate = ref.iloc[i]
        evd_ids = [int(_) for _ in investigate['Evidence IDs'].split(';')]
        subset = evd.loc[evd_ids].copy()

        subset['protein_group'] =  investigate['Protein IDs']
        subset['sample_group'] = subset['Experiment']
        subset['fraction'] = subset['Fraction']
        subset['precursor']  = ['_'.join(_) for _ in zip(subset['Sequence'].values, subset['Charge'].values.astype('str'))]

        protein_df.append(subset)

        if callback:
            callback((i+1)/len(ref))

    logging.info(f'A total of {max_:,} proteins.')

    df = pd.concat(protein_df)

    field = 'Intensity'

    if delayed:
        df, normed = delayed_normalization(df, field ='Intensity', minimum_occurence = minimum_occurence)
        field = 'Intensity_dn'

    protein_table = protein_profile_parallel(df, minimum_ratios=minimum_ratios, field=field, callback=callback)

    return protein_table