# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/09_matching.ipynb (unless otherwise specified).

__all__ = ['calculate_distance', 'calib_table', 'align', 'calculate_deltas', 'align_files', 'align_datasets',
           'get_probability', 'convert_decoy', 'match_datasets']

# Cell

import pandas as pd
import numpy as np

def calculate_distance(table_1: pd.DataFrame, table_2: pd.DataFrame, offset_dict: dict, calib: bool = False) -> (list, int):
    """Calculate the distance between two precursors for different columns
    Distance can either be relative or absolute.

    An example for a minimal offset_dict is: offset_dict = {'mass':'absolute'}

    Args:
        table_1 (pd.DataFrame): Dataframe with precusor data.
        table_2 (pd.DataFrame): Dataframe with precusor data.
        offset_dict (dict): Dictionary with column names and how the distance should be calculated.
        calib (bool): Flag to indicate that distances should be calculated on calibrated columns. Defaults to False.

    Raises:
        KeyError: If either table_1 or table_2 is not indexed by precursor

    """

    if table_1.index.name != 'precursor':
        raise KeyError('table_1 is not indexed by precursor')

    if table_2.index.name != 'precursor':
        raise KeyError('table_2 is not indexed by precursor')

    shared_precursors = list(set(table_1.index).intersection(set(table_2.index)))

    table_1_ = table_1.loc[shared_precursors]
    table_2_ = table_2.loc[shared_precursors]

    table_1_ = table_1_.groupby('precursor').mean()
    table_2_ = table_2_.groupby('precursor').mean()

    deltas = []

    for col in offset_dict:
        if calib:
            col_ = col+'_calib'
        else:
            col_ = col

        if offset_dict[col] == 'absolute':
            deltas.append(np.nanmedian(table_1_[col_] - table_2_[col_]))
        elif offset_dict[col] == 'relative':
            deltas.append(np.nanmedian((table_1_[col_] - table_2_[col_]) / (table_1_[col_] + table_2_[col_]) * 2))
        else:
            raise NotImplementedError(f"Calculating delta for {offset_dict[col_]} not implemented.")

    return deltas, len(shared_precursors)

# Cell

def calib_table(table: pd.DataFrame, delta: pd.Series, offset_dict: dict):
    """
    Apply offset to a table. Different operations for offsets exist.
    Offsets will be saved with a '_calib'-suffix. If this does not already exist,
    it will be created.

    Args:
        table_1 (pd.DataFrame): Dataframe with data.
        delta (pd.Series): Series cotaining the offset.
        offset_dict (dict): Dictionary with column names and how the distance should be calculated.

    Raises:
        NotImplementedError: If the type of vonversion is not implemented.
    """
    for col in offset_dict:

        if (col not in table.columns) and (col+'_apex' in table.columns):
            col_ = col+'_apex'
        else:
            col_ = col

        if offset_dict[col] == 'absolute':
            table[col+'_calib'] =  table[col_]-delta[col]
        elif offset_dict[col] == 'relative':
            table[col+'_calib'] = (1-delta[col_])*table[col]
        else:
            raise NotImplementedError(offset_dict[col])

# Cell
import logging
from sklearn.linear_model import LinearRegression
import sys

def align(deltas: pd.DataFrame, filenames: list, weights:np.ndarray=None, n_jobs=None) -> np.ndarray:
    """Align multiple datasets.
    This function creates a matrix to represent the shifts from each dataset to another.
    This effectively is an overdetermined equation system and is solved with a linear regression.

    Args:
        deltas (pd.DataFrame): Distances from each dataset to another.
        filenames (list): The filenames of the datasts that were compared.
        weights (np.ndarray, optional): Distances can be weighted by their number of shared elements. Defaults to None.
        n_jobs (optional): Number of processes to be used. Defaults to None (=1).

    Returns:
        np.ndarray: alignment values.
    """
    matrix = []

    for i in range(len(deltas)):
        start, end = deltas.index[i]

        start_idx = filenames.index(start)
        end_idx = filenames.index(end)

        lines = np.zeros(len(filenames)-1)
        lines[start_idx:end_idx] = 1
        matrix.append(lines)

    # Remove nan values
    not_nan = ~deltas.isnull().any(axis=1)
    matrix = np.array(matrix)
    matrix = matrix[not_nan]
    deltas_ = deltas[not_nan]

    if len(deltas) < matrix.shape[1]:
        logging.info('Low overlap between datasets detected. Alignment may fail.')

    if weights is not None:
        reg = LinearRegression(fit_intercept=False, n_jobs=n_jobs).fit(matrix, deltas_.values, sample_weight = weights[not_nan])
        score= reg.score(matrix, deltas_.values)
    else:
        reg = LinearRegression(fit_intercept=False, n_jobs=n_jobs).fit(matrix, deltas_.values)
        score= reg.score(matrix, deltas_.values)

    logging.info(f"Regression score is {score}")

    x = reg.predict(np.eye(len(filenames)-1))

    return x

# Cell
import alphapept.io
import os
from typing import Callable

def calculate_deltas(combos: list, calib:bool = False, callback:Callable=None) -> (pd.DataFrame, np.ndarray, dict):

    """Wrapper function to calculate the distances of multiple files.

    In here, we define the offset_dict to make a relative comparison for mz and mobility and absolute for rt.

    TODO: This function could be speed-up by parallelization

    Args:
        combos (list): A list containing tuples of filenames that should be compared.
        calib (bool): Boolean flag to indicate distance should be calculated on calibrated data.
        callback (Callable): A callback function to track progress.

    Returns:
        pd.DataFrame: Dataframe containing the deltas of the files
        np.ndarray: Numpy array containing the weights of each comparison (i.e. number of shared elements)
        dict: Offset dictionary whicch was used for comparing.

    """

    offset_dict = {}
    deltas = pd.DataFrame()
    weights = []

    for i, combo in enumerate(combos):
        file1 = os.path.splitext(combo[0])[0] + '.ms_data.hdf'
        file2 = os.path.splitext(combo[1])[0] + '.ms_data.hdf'
        df_1 = alphapept.io.MS_Data_File(file1).read(dataset_name="peptide_fdr").set_index('precursor')
        df_2 = alphapept.io.MS_Data_File(file2).read(dataset_name="peptide_fdr").set_index('precursor')

        if not offset_dict:
            offset_dict = {'mz':'relative', 'rt':'absolute'}
            if 'mobility' in df_1.columns:
                logging.info("Also using mobility for calibration.")
                offset_dict['mobility'] = 'relative'
            cols = list(offset_dict.keys())

        if len(deltas) == 0:
             deltas = pd.DataFrame(columns = cols)

        dists, weight = calculate_distance(df_1, df_2, offset_dict, calib = calib)
        deltas = deltas.append(pd.DataFrame([dists], columns = cols, index=[combo]))

        weights.append(weight)

        if callback:
            callback((i+1)/len(combos))

    return deltas, np.array(weights), offset_dict

# Cell
import pandas as pd
from itertools import combinations
import numpy as np
import os
import functools

#There is no unit test for align_files and align_datasets as they are wrappers and should be covered by the quick_test
def align_files(filenames: list, alignment: pd.DataFrame, offset_dict: dict):
    """
    Wrapper function that aligns a list of files.

    Args:
        filenames (list): A list with raw file names.
        alignment (pd.DataFrame): A pandas dataframe containing the alignment information.
        offset_dict (dict): Dictionary with column names and how the distance should be calculated.
    """
    for idx, filename in enumerate(filenames):

        file = os.path.splitext(filename)[0] + '.ms_data.hdf'

        for column in ['peptide_fdr', 'feature_table']:
            df = alphapept.io.MS_Data_File(file).read(dataset_name=column)
            calib_table(df, alignment.iloc[idx], offset_dict)
            logging.info(f"Saving {file} - {column}.")
            ms_file = alphapept.io.MS_Data_File(file, is_overwritable=True)

            ms_file.write(df, dataset_name=column)


def align_datasets(settings:dict, callback:callable=None):
    """
    Wrapper function that aligns all experimental files specified a settings file.

    Args:
        settings (dict): A list with raw file names.
        callback (Callable): Callback function to indicate progress.
    """
    filenames = settings['experiment']['file_paths']

    if callback:
        def progress_wrapper(step, n_steps, current):
            callback((step/n_steps)+(current/n_steps))

        progress_wrapper(0, 2, 0)
        cb = functools.partial(progress_wrapper, 0, 2)
    else:
        cb = None

    if len(filenames) > 1:
        combos = list(combinations(filenames, 2))

        deltas, weights, offset_dict = calculate_deltas(combos, callback=cb)

        cols = list(offset_dict.keys())

        before_sum = deltas.abs().sum().to_dict()
        before_mean = deltas.abs().mean().to_dict()

        logging.info(f'Total deviation before calibration {before_sum}')
        logging.info(f'Mean deviation before calibration {before_mean}')

        n_jobs = settings['general']['n_processes']

        logging.info(f'Solving equation system with {n_jobs} jobs.')

        alignment = pd.DataFrame(align(deltas, filenames, weights, n_jobs), columns = cols)
        alignment = pd.concat([alignment, pd.DataFrame(np.zeros((1, alignment.shape[1])), columns= cols)])

        alignment -= alignment.mean()

        logging.info(f'Solving equation system complete.')

        logging.info(f'Applying offset')

        align_files(filenames, alignment, offset_dict)

        if cb:
            progress_wrapper(0, 2, 1)
            cb = functools.partial(progress_wrapper, 1, 2)

        deltas, weights, offset_dict = calculate_deltas(combos, calib=True, callback=cb)

        after_sum = deltas.abs().sum().to_dict()
        after_mean = deltas.abs().mean().to_dict()

        logging.info(f'Total deviation after calibration {after_sum}')
        logging.info(f'Mean deviation after calibration {after_mean}')

        change_sum = {k:v/before_sum[k] for k,v in after_sum.items()}
        change_mean = {k:v/before_mean[k] for k,v in after_mean.items()}

        logging.info(f'Change (after/before) total deviation {change_sum}')
        logging.info(f'Change (after/before) mean deviation {change_mean}')

    else:
        logging.info('Only 1 dataset present. Skipping alignment.')

# Cell
from scipy import stats
def get_probability(df: pd.DataFrame, ref: pd.DataFrame, sigma:pd.DataFrame, index:int)-> float:
    """Probablity estimate of a transfered identification using the Mahalanobis distance.

    The function calculates the probability that a feature is a reference feature.
    The reference features containing std deviations so that a probability can be estimated.

    It is required that the data frames are matched, meaning that the first entry in df matches to the first entry in ref.

    Args:
        df (pd.DataFrame): Dataset containing transferered features
        ref (pd.DataFrame): Dataset containing reference features
        sigma (pd.DataFrame): Dataset containing the standard deviations of the reference features
        index (int): Index to the datframes that should be compared

    Returns:
        float: Mahalanobis distance
    """

    sigma = sigma.iloc[index].values
    sigma = sigma*np.eye(len(sigma))

    mu = ref.iloc[index].values
    x = df.iloc[index].values

    try:
        m_dist_x = np.dot((x-mu).transpose(), np.linalg.inv(sigma))
        m_dist_x = np.dot(m_dist_x, (x-mu))
        _ = stats.chi2.cdf(m_dist_x, len(mu))
    except Exception as e:
        _ = np.nan

    return _

# Cell
from sklearn.neighbors import KDTree
from .utils import assemble_df

def convert_decoy(float_):
    """
    Utility function to convert type for decoy after grouping.

    """
    if float_ == 1:
        return True
    else:
        return False

# This function is a wrapper function and has currently has no unit test
# The function will be revised when implementing issue #255: https://github.com/MannLabs/alphapept/issues/255
def match_datasets(settings:dict, callback:Callable = None):
    """Match datasets: Wrapper function to match datasets based on a settings file.
    This implementation uses matching groups but not fractions.

    Args:
        settings (dict): Dictionary containg specifications of the run
        callback (Callable): Callback function to indicate progress.
    """


    if len(settings['experiment']['file_paths']) > 2:

        if settings['experiment']['matching_group'] == []:
            settings['experiment']['matching_group'] = [0 for _ in settings['experiment']['shortnames']]

        match_p_min = settings['matching']['match_p_min']
        match_d_min = settings['matching']['match_d_min']

        filenames = settings['experiment']['file_paths']

        shortnames_lookup = dict(zip(settings['experiment']['shortnames'], settings['experiment']['file_paths']))

        matching_group = np.array(settings['experiment']['matching_group'])
        n_matching_group = len(set(matching_group))
        match_tolerance = settings['matching']['match_group_tol']
        logging.info(f'A total of {n_matching_group} matching groups set.')

        x = alphapept.utils.assemble_df(settings, field='peptide_fdr')

        logging.info(f'A total of {len(x):,} peptides for matching in peptide_fdr.')

        base_col = ['precursor']
        alignment_cols = ['mz_calib','rt_calib']
        extra_cols = ['score','decoy','target']

        if 'mobility' in x.columns:
            alignment_cols += ['mobility_calib']
            use_mobility = True
        else:
            use_mobility = False

        for group in set(settings['experiment']['matching_group']):
            logging.info(f'Matching group {group} with a tolerance of {match_tolerance}.')
            file_index_from = (matching_group <= (group+match_tolerance)) & (matching_group >= (group-match_tolerance))
            file_index_to = matching_group == group
            files_from = np.array(settings['experiment']['shortnames'])[file_index_from].tolist()
            files_to = np.array(settings['experiment']['shortnames'])[file_index_to].tolist()
            logging.info(f'Matching from {len(files_from)} files to {len(files_to)} files.')
            logging.info(f'Matching from {files_from} to {files_to}.')

            if len(files_from) > 2:
                xx = x[x['shortname'].apply(lambda x: x in files_from)].copy()

                grouped = xx[base_col + alignment_cols + extra_cols].groupby('precursor').mean()

                grouped['decoy'] = grouped['decoy'].apply(lambda x: convert_decoy(x))
                grouped['target'] = grouped['target'].apply(lambda x: convert_decoy(x))

                std_ = xx[base_col + alignment_cols].groupby('precursor').std()

                grouped[[_+'_std' for _ in alignment_cols]] = std_

                std_range = np.nanmedian(std_.values, axis=0)

                lookup_dict = xx.set_index('precursor')[['sequence','sequence_naked','db_idx']].to_dict()

                for file_to in files_to:
                    filename = shortnames_lookup[file_to]
                    file = os.path.splitext(filename)[0] + '.ms_data.hdf'

                    df = alphapept.io.MS_Data_File(file).read(dataset_name='peptide_fdr')
                    features = alphapept.io.MS_Data_File(file).read(dataset_name='feature_table')
                    features['feature_idx'] = features.index

                    matching_set = set(grouped.index) - set(df['precursor'])
                    logging.info(f'Trying to match file {file} with database of {len(matching_set):,} unidentified candidates')

                    mz_range = std_range[0]
                    rt_range = std_range[1]

                    tree_points = features[alignment_cols].values
                    tree_points[:,0] = tree_points[:,0]/mz_range
                    tree_points[:,1] = tree_points[:,1]/rt_range

                    query_points = grouped.loc[matching_set][alignment_cols].values
                    query_points[:,0] = query_points[:,0]/mz_range
                    query_points[:,1] = query_points[:,1]/rt_range

                    if use_mobility:
                        logging.info("Using mobility")
                        i_range = std_range[2]

                        tree_points[:,2] = tree_points[:,2]/i_range
                        query_points[:,2] = query_points[:,2]/i_range

                    matching_tree = KDTree(tree_points, metric="euclidean")

                    dist, idx = matching_tree.query(query_points, k=1)

                    matched = features.iloc[idx[:,0]].reset_index(drop=True)

                    for _ in extra_cols:
                        matched[_] = grouped.loc[matching_set, _].values

                    to_keep = dist < match_d_min

                    matched = matched[to_keep]

                    ref = grouped.loc[matching_set][alignment_cols][to_keep]
                    sigma = std_.loc[matching_set][to_keep]

                    logging.info(f'{len(matched):,} possible features for matching based on distance of {match_d_min}')

                    matched['matching_p'] = [get_probability(matched[alignment_cols], ref, sigma, i) for i in range(len(matched))]
                    matched['precursor'] = grouped.loc[matching_set][to_keep].index.values
                    matched['score'] = grouped.loc[matching_set][to_keep]['score'].values

                    matched = matched[matched['matching_p']< match_p_min]

                    logging.info(f'{len(matched):,} possible features for matching based on probability of {match_p_min}')

                    matched['type'] = 'matched'

                    for _ in lookup_dict.keys():
                        matched[_] = [lookup_dict[_][x] for x in matched['precursor']]

                    df['type'] = 'msms'
                    df['matching_p'] = np.nan

                    shared_columns = set(matched.columns).intersection(set(df.columns))

                    df_ = pd.concat([df, matched[shared_columns]], ignore_index=True)

                    logging.info(f"Saving {file} - peptide_fdr.")
                    ms_file = alphapept.io.MS_Data_File(file, is_overwritable=True)

                    ms_file.write(df_, dataset_name='peptide_fdr')

            else:
                logging.info(f'Less than 3 datasets present in matching group {group}. Skipping matching.')

    else:
        logging.info('Less than 3 datasets present. Skipping matching.')

    logging.info('Matching complete.')