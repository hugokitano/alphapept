#Analyze statistics
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import alphapept.io
import os
import alphapept.io
import seaborn as sns
from tqdm.notebook import tqdm as tqdm
import warnings


import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm
from matplotlib.colors import Normalize
from scipy.interpolate import interpn

COLOR_1 = 'r'
COLOR_2 = 'b'

def density_scatter( x , y, ax = None, sort = True, bins = 30, cmap = 'turbo', **kwargs )   :
    """
    Scatter plot colored by 2d histogram
    Adapted from https://stackoverflow.com/questions/20105364/how-can-i-make-a-scatter-plot-colored-by-density-in-matplotlib
    """

    data , x_e, y_e = np.histogram2d( x, y, bins = bins, density = True )
    z = interpn( ( 0.5*(x_e[1:] + x_e[:-1]) , 0.5*(y_e[1:]+y_e[:-1]) ) , data , np.vstack([x,y]).T , method = "splinef2d", bounds_error = False)

    #To be sure to plot all data
    z[np.where(np.isnan(z))] = 0.0

    # Sort the points by density, so that the densest points are plotted last
    if sort :
        idx = z.argsort()
        x, y, z = x[idx], y[idx], z[idx]

    ax.scatter( x, y, c=z, cmap=cmap, **kwargs )

    return ax

def prepare_files(path1, path2):

    df1 = pd.read_hdf(path1, 'protein_fdr')

    # add sequence charge
    df1['missed_cleavages'] = df1['sequence'].str[:-1].str.count('K') + df1['sequence'].str[:-1].str.count('R')

    #Convert maxquant
    df2 = pd.read_csv(path2, sep='\t')
    df2['charge'] = df2['Charge']

    list_2 = df2['Modified sequence'].values
    list_2 = [alphapept.io.parse_mq_seq(_) for _ in list_2]
    df2['sequence'] = list_2

    df2['precursor'] = ['_'.join(_) for _ in zip(list_2, df2['Charge'].values.astype('int').astype('str'))]
    df2['protein'] = df2['Leading razor protein']
    df2['decoy'] = df2['Reverse'] == '+'
    df2['score'] = df2['Score']
    df2['ms1_int_sum'] = df2['Intensity']
    df2['missed_cleavages'] = df2['sequence'].str[:-1].str.count('K') + df2['sequence'].str[:-1].str.count('R')

    return df1, df2


def compare_field(df1, df2, software_1, software_2, field, exclude_decoy=True):

    title_dict = {'protein':'Number of unique proteins',
                 'sequence': 'Number of unique peptide sequences',
                 'precursor':'Number of unique sequence/charge combinations',
                 'charge':'Occurence of charge states',
                 'digestion':'Occurence of last AA in sequence',
                 'total_missed_cleavages':'Total number of missed cleavages',
                 'missed_cleavages':'Ratio of number of of missed cleavages'}#nicer descriptions for the plots

    if exclude_decoy:
        df1 = df1[~df1['decoy']]
        df2 = df2[~df2['decoy']]

    #Some pre-defined boundaries
    plt.figure(figsize=(5,5))

    if field == 'charge':
        ratios = df1[field].value_counts() / df2[field].value_counts()
        plt.axhline(1, color='k', linestyle=':')
        plt.bar(ratios.index, ratios.values, label='Ratio {}/{}'.format(software_1, software_2))
        plt.legend()
        #bins = np.arange(1,6,0.5)

        #plt.hist(df1[field].values, bins=bins,label=software_1)
        #plt.hist(df2[field].values-0.5, bins=bins, label=software_2)

        plt.legend()

    elif (field == 'protein') or (field == 'sequence') or (field == 'precursor'):
        plt.bar(software_1, len(set(df1[field])))
        plt.bar(software_2, len(set(df2[field])))

    elif (field == 'digestion'):
        ratios = df1['sequence'].str[-1].value_counts() / df2['sequence'].str[-1].value_counts()
        plt.axhline(1, color='k', linestyle=':')
        plt.bar(ratios.index, ratios.values, label='Ratio {}/{}'.format(software_1, software_2))
        plt.legend()


    elif (field == 'total_missed_cleavages'):
        field_ = 'missed_cleavages'
        plt.bar(software_1, df1[field_].sum())
        plt.bar(software_2, df2[field_].sum())


    elif (field == 'missed_cleavages'):
        ratios = df1[field].value_counts() / df2[field].value_counts()
        plt.axhline(1, color='k', linestyle=':')
        plt.bar(ratios.index, ratios.values, label='Ratio {}/{}'.format(software_1, software_2))

    else:
        raise NotImplementedError

    plt.title(title_dict[field])
    plt.show()


from matplotlib_venn import venn2
def compare_populations(df1, df2, software_1, software_2, field, exclude_decoy=True):
    """
    Compare to lists of peptides / proteins
    Convention: all should be uppercase
    ToDo: check this maybe
    """

    title_dict = {'protein':'Shared proteins',
                 'sequence': 'Shared peptide sequences',
                 'precursor':'Shared sequence/charge combinations',
                 }

    if exclude_decoy:
        df1 = df1[~df1['decoy']]
        df2 = df2[~df2['decoy']]

    list_1 = df1[field].values
    list_2 = df2[field].values

    peptides_1 = set(list_1)
    peptides_2 = set(list_2)
    n_1 = len(peptides_1 - peptides_2)
    n_2 = len(peptides_2 - peptides_1)
    shared = len(peptides_1.intersection(peptides_2))

    venn2(subsets = (n_1, n_2, shared), set_labels = (software_1, software_2))
    plt.title(title_dict[field])
    plt.show()

def compare_intensities(df1, df2,software_1, software_2):
    ref_df1 = df1.copy()
    ref_df2 = df2.copy()

    f, (ax1, ax2) = plt.subplots(1, 2, sharey=True,sharex=True, figsize=(10,5))

    axes = [ax1, ax2]

    for idx, _ in enumerate(['protein','precursor']):

        ax = axes[idx]
        d1 = np.log(ref_df1[[_,'fragments_int_sum']].groupby(_).sum())
        d2 = np.log(ref_df2[[_,'ms1_int_sum']].groupby(_).sum())

        d2 = d2[~np.isinf(d2['ms1_int_sum'].values)]

        shared = set(d1.index.values).intersection(set(d2.index.values))

        ax = density_scatter(d1.loc[shared]['fragments_int_sum'].values, d2.loc[shared]['ms1_int_sum'].values, ax = ax, bins=30)

        ax.set_xlabel(software_1)
        ax.set_ylabel(software_2)
        ax.set_title(f"{_} intensity n={len(shared):,}")


    mins_ = []
    maxs_ = []

    for idx, _ in enumerate(['protein','precursor']):
        ax = axes[idx]

        ylim = ax.get_ylim()
        xlim = ax.get_xlim()

        mins_.append(ylim[0])
        maxs_.append(ylim[1])

        mins_.append(xlim[0])
        maxs_.append(xlim[1])

    min_ = np.min(mins_)
    max_ = np.max(maxs_)

    for idx, _ in enumerate(['protein','precursor']):
        ax = axes[idx]
        ax.plot([min_, max_], [min_, max_], 'k:', alpha=0.7)

    plt.show()


def protein_rank(df1, df2, software_1, software_2):
    data_1 = df1[['protein','fragments_int_sum']].groupby('protein').sum()
    data_1 = data_1.sort_values(by='fragments_int_sum', ascending=False) #.head(20)
    data_1 = data_1[data_1>0]

    data_2 = df2[['Leading proteins','Intensity']].groupby('Leading proteins').sum()
    data_2 = data_2.sort_values(by='Intensity', ascending=False) #.head(20)
    data_2 = data_2[data_2>0]

    data_1 = df1[['protein','fragments_int_sum']].groupby('protein').sum()
    data_1 = data_1.sort_values(by='fragments_int_sum', ascending=False) #.head(20)
    data_1 = data_1.reset_index()
    data_1 = data_1[data_1['fragments_int_sum']>0]

    data_2 = df2[['Leading proteins','Intensity']].groupby('Leading proteins').sum()
    data_2 = data_2.sort_values(by='Intensity', ascending=False) #.head(20)
    data_2 = data_2.reset_index()
    data_2 = data_2[data_2['Intensity']>0]

    fig, axes = plt.subplots(1, 1, figsize=(5,5), sharex=True,sharey=True)

    ax1 = axes

    ax1.plot(data_1['fragments_int_sum'].values, label=software_1, color='r')
    ax1.axhline(data_1['fragments_int_sum'].min(), color='r', linestyle=':')
    ax1.axhline(data_1['fragments_int_sum'].max(), color='r', linestyle=':')

    ax1.plot(data_2['Intensity'].values, label=software_2, color='b')
    ax1.axhline(data_2['Intensity'].min(), color='b', linestyle=':')
    ax1.axhline(data_2['Intensity'].max(), color='b', linestyle=':')
    ax1.set_yscale('log')
    ax1.legend()
    ax1.set_ylabel('Protein Intensity')
    plt.show()


def get_plot_df(ref, base_columns, ratio_columns, ax, id_, valid_filter = True):

    to_plot = pd.DataFrame()
    ref[base_columns] = ref[base_columns].replace(0, np.nan)
    ref[ratio_columns] = ref[ratio_columns].replace(0, np.nan)
    to_plot['Species'] = ref['Species']

    to_plot['base'] = ref[base_columns].median(axis=1)
    to_plot['ratio'] = ref[ratio_columns].median(axis=1)
    to_plot['base_cnt'] = ref[base_columns].notna().sum(axis=1)
    to_plot['ratio_cnt'] = ref[ratio_columns].notna().sum(axis=1)

    to_plot['ratio_'] = np.log2(to_plot['base'] / to_plot['ratio'])
    to_plot['sum_'] = np.log2(to_plot['ratio'])

    if valid_filter:
        valid = to_plot.query(f'ratio_cnt >= 2 and base_cnt >=2')
    else:
        valid = to_plot.query(f'ratio_cnt >0 and base_cnt >0')

    homo = valid[valid['Species'] == 'Homo sapiens']
    e_coli = valid[valid['Species'] == 'Escherichia coli']

    homo_ratio = homo['ratio_'].values
    e_coli_ratio = e_coli['ratio_'].values

    ax = density_scatter(homo['ratio_'].values, homo['sum_'].values, ax, bins=20, cmap='Reds', alpha=0.5)
    ax = density_scatter(e_coli['ratio_'].values, e_coli['sum_'].values, ax, bins=20, cmap='Blues', alpha=0.5)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        homo_ratio_median = np.nanmedian(homo_ratio[~np.isinf(homo_ratio)])
        e_coli_ratio_median = np.nanmedian(e_coli_ratio[~np.isinf(e_coli_ratio)])

        homo_ratio_std = np.nanstd(homo_ratio[~np.isinf(homo_ratio)])
        e_coli_ratio_std = np.nanstd(e_coli_ratio[~np.isinf(e_coli_ratio)])

    nl = '\n'
    ax.set_title(f'{id_} {nl} Homo (median, std) {homo_ratio_median:.2f}, {homo_ratio_std:.2f} {nl} EColi (median, std) {e_coli_ratio_median:.2f}, {e_coli_ratio_std:.2f} {nl} {valid["Species"].value_counts().to_dict()}')

def get_plot_df_single(ref, base_columns, ratio_columns, ax, id_, valid_filter = True):

    to_plot = pd.DataFrame()
    ref[base_columns] = ref[base_columns].replace(0, np.nan)
    ref[ratio_columns] = ref[ratio_columns].replace(0, np.nan)
    to_plot['Species'] = ref['Species']

    to_plot['base'] = ref[base_columns].median(axis=1)
    to_plot['ratio'] = ref[ratio_columns].median(axis=1)
    to_plot['base_cnt'] = ref[base_columns].notna().sum(axis=1)
    to_plot['ratio_cnt'] = ref[ratio_columns].notna().sum(axis=1)

    to_plot['ratio_'] = np.log2(to_plot['base'] / to_plot['ratio'])
    to_plot['sum_'] = np.log2(to_plot['ratio'])

    if valid_filter:
        valid = to_plot.query(f'ratio_cnt >= 2 and base_cnt >=2')
    else:
        valid = to_plot.query(f'ratio_cnt >0 and base_cnt >0')

    homo = valid[valid['Species'] == 'Homo sapiens']
    e_coli = valid[valid['Species'] == 'Escherichia coli']

    homo_ratio = homo['ratio_'].values
    e_coli_ratio = e_coli['ratio_'].values

    ax = density_scatter(valid['ratio_'].values, valid['sum_'].values, ax, bins=30)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        homo_ratio_median = np.nanmedian(homo_ratio[~np.isinf(homo_ratio)])
        e_coli_ratio_median = np.nanmedian(e_coli_ratio[~np.isinf(e_coli_ratio)])

        homo_ratio_std = np.nanstd(homo_ratio[~np.isinf(homo_ratio)])
        e_coli_ratio_std = np.nanstd(e_coli_ratio[~np.isinf(e_coli_ratio)])

    nl = '\n'
    ax.set_title(f'{id_} {nl} Homo (median, std) {homo_ratio_median:.2f}, {homo_ratio_std:.2f} {nl} EColi (median, std) {e_coli_ratio_median:.2f}, {e_coli_ratio_std:.2f} {nl} {valid["Species"].value_counts().to_dict()}')



def algorithm_test(evd, ref, base_columns, ratio_columns, base_columns2, ratio_columns2, test_id, software_1, software_2):
    spec_dict = {}
    all_points = []
    species_ = []

    experiments = evd['Raw file'].unique().tolist()

    protein_idx = []

    for i in tqdm(range(len(ref))):

        investigate = ref.iloc[i]
        evd_ids = [int(_) for _ in investigate['Evidence IDs'].split(';')]
        species = investigate['Species']
        subset = evd.loc[evd_ids].copy()

        field_ = 'Intensity'

        subset['protein'] = 'X'
        subset['filename'] = subset['Raw file']
        subset['precursor']  = ['_'.join(_) for _ in zip(subset['Modified sequence'].values, subset['Charge'].values.astype('str'))]
        protein = 'X'


        from alphapept.quantification import protein_profile

        profile, pre_lfq, experiment_ids, protein = protein_profile(subset, experiments, field_, protein)
        xx = pd.DataFrame([profile, pre_lfq], columns=experiment_ids).T
        xx.columns = ['lfq_ap', 'int_ap']

        all_points.append(xx[['lfq_ap']].T)
        protein_idx.append(i)
        species_.append(species)

    df = pd.concat(all_points)
    df.index = protein_idx
    df['Species'] = species_

    fig, axes = plt.subplots(1, 2, figsize=(14,7), sharex=True,sharey=True)

    id_ = f'{software_2} {test_id}'
    get_plot_df(ref, base_columns, ratio_columns, axes[0], id_)

    id_ = f'{software_1} on {software_2} {test_id}'
    get_plot_df(df, base_columns2, ratio_columns2, axes[1], id_)


import pandas as pd
import numpy as np
import random

def generate_peptide_list(num_peps):
    """simulate a list of peptide names"""
    pepcount = 0
    count = 0
    peptides = []
    while count < num_peps:
        list = [f'pep{pepcount}']

        for levelidx, level in enumerate([2]):
            num_events = np.random.randint(1,level)
            new_list = []
            for elem in list:
                for idx in range(num_events):
                    new_list.append(elem + f"_LVL{levelidx}_mod{idx}")
                    count+=1
            list = new_list
        peptides.extend(list)
        pepcount+=1

    return peptides

def generate_protein_list(pepnames):
    """simulate protein names for a list of peptide names"""
    res = []
    assigned = 0
    protcount = 0
    while assigned < len(pepnames):
        protstring = f"P{protcount}"
        num_peps = random.randint(2,10)
        for i in range(num_peps):
            res.append(protstring)
        assigned+=num_peps
        protcount+=1
    res = res[:len(pepnames)]
    return res

def simulate_biased_peptides(num_pep, samplevec, fractionvec):
    """generate a dataframe with simuated peptides belonging to different fractions and samples.
    Systematic shifts are simulated into the samples

    Args:
        num_pep (int): number of peptides to simulate
        samplevec (list[String]): each entry corresponds to one "fake sample"
        fractionvec (list[int]): list of same length as above, each entry gives the number of fractions to simulate for the fake sample



    Returns:
        dataframe: dataframe in the same format as "real" peptides

    Example:
     simulate_biased_peptides(20000, ["A", "B"], [3, 5]) simulates a dataset consisting of sample A with 3 fractions and sample B with 5 fractions
    """
    pepnames = generate_peptide_list(num_pep) #gives uuid strings for each peptide
    protnames = generate_protein_list(pepnames)
    pep2prot = {pep:prot for pep, prot in zip(pepnames, protnames)}

    pep_idxs = list(range(len(pepnames)))
    pep2baseint = { name : np.abs(np.random.lognormal(5))*1000 for name in pepnames}


    shortname = [] #sample names
    precursor = []
    fraction = []
    intensity = []

    for idx_samp in range(len(samplevec)):
        sample = samplevec[idx_samp]
        num_fractions = fractionvec[idx_samp]
        peps_per_frac = int(len(pepnames)/num_fractions)
        start_idx = 0
        for frac_idx in range(num_fractions):
            #set df columns for given fraction
            shift_factor = np.random.uniform(low=1, high=100)
            random.shuffle(pep_idxs)
            selected_pep_idxs = pep_idxs[start_idx:start_idx +peps_per_frac]
            precursors_local = [pepnames[x] for x in selected_pep_idxs]
            shortname_local = [sample for x in precursors_local]
            fraction_local = [frac_idx for x in precursors_local]
            intensity_local = [(np.random.standard_normal()+shift_factor)*pep2baseint.get(x) for x in precursors_local]

            #extend global lists
            shortname.extend(shortname_local)
            precursor.extend(precursors_local)
            fraction.extend(fraction_local)
            intensity.extend(intensity_local)

            start_idx+= peps_per_frac


    proteins = [pep2prot.get(x) for x in precursor]
    species = ['X' for x in precursor]
    df_simul = pd.DataFrame({"protein_group": proteins, "precursor": precursor, "sample_group" : shortname,"fraction": fraction, "Intensity" : intensity,
    'Species' : species})

    return df_simul

def add_species_column(prot_df_mq):
    if 'Species' in prot_df_mq.keys():
        return
    prots = prot_df_mq["Protein IDs"]
    species = []
    for prot in prots:
        if "_ECO" in prot:
            species.append('Escherichia coli')
        elif "HUMAN" in prot:
            species.append("Homo sapiens")
        else:
            species.append("X")
    prot_df_mq['Species'] = species
