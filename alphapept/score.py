# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/06_score.ipynb (unless otherwise specified).

__all__ = ['filter_score', 'filter_precursor', 'get_q_values', 'cut_fdr', 'cut_global_fdr', 'get_x_tandem_score',
           'score_x_tandem', 'filter_with_x_tandem', 'score_psms', 'get_ML_features', 'train_RF', 'score_ML',
           'filter_with_ML', 'get_unique_proteins', 'get_shared_proteins', 'get_protein_groups',
           'perform_protein_grouping', 'get_ion', 'score_hdf', 'ion_dict', 'protein_groups_hdf', 'protein_grouping_all',
           'protein_groups_hdf_parallel']

# Cell
import numpy as np
import pandas as pd
import logging
import alphapept.io

def filter_score(df, mode='multiple'):
    """
    Filter df by score
    TODO: PSMS could still have the same score when having modifications at multiple positions that are not distinguishable.
    Only keep one.

    """
    df["rank"] = df.groupby("query_idx")["score"].rank("dense", ascending=False).astype("int")
    df = df[df["rank"] == 1]

    # in case two hits have the same score and therfore rank only accept the first one
    df = df.drop_duplicates("query_idx")

    if 'dist' in df.columns:
        df["feature_rank"] = df.groupby("feature_idx")["dist"].rank("dense", ascending=True).astype("int")
        df["raw_rank"] = df.groupby("raw_idx")["score"].rank("dense", ascending=False).astype("int")

        if mode == 'single':
            df_filtered = df[(df["feature_rank"] == 1) & (df["raw_rank"] == 1) ]
            df_filtered = df_filtered.drop_duplicates("raw_idx")

        elif mode == 'multiple':
            df_filtered = df[(df["feature_rank"] == 1)]

        else:
            raise NotImplementedError('Mode {} not implemented yet'.format(mode))

    else:
        df_filtered = df

    # TOD: this needs to be sorted out, for modifications -> What if we have MoxM -> oxMM, this will screw up with the filter sequence part
    return df_filtered

def filter_precursor(df):
    """
    Filter df by precursor
    Allow each precursor only once.

    """
    df["rank_precursor"] = (
        df.groupby("precursor")["score"].rank("dense", ascending=False).astype("int")
    )
    df_filtered = df[df["rank_precursor"] == 1]

    return df_filtered

# Cell
from numba import njit
@njit
def get_q_values(fdr_values):
    """
    Calculate q values from fdr_values
    """
    q_values = np.zeros_like(fdr_values)
    min_q_value = np.max(fdr_values)
    for i in range(len(fdr_values) - 1, -1, -1):
        fdr = fdr_values[i]
        if fdr < min_q_value:
            min_q_value = fdr
        q_values[i] = min_q_value

    return q_values

# Cell
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def cut_fdr(df, fdr_level=0.01, plot=True):
    """
    Cuts a dataframe with a given fdr level

    Args:
        fdr_level: fdr level that should be used
        plot: flag to enable plot

    Returns:
        cutoff: df with psms within fdr
        cutoff_value: numerical value of score cutoff

    Raises:

    """

    df["target"] = ~df["decoy"]

    df = df.sort_values(by=["score","decoy"], ascending=False)
    df = df.reset_index()

    df["target_cum"] = np.cumsum(df["target"])
    df["decoys_cum"] = np.cumsum(df["decoy"])

    df["fdr"] = df["decoys_cum"] / df["target_cum"]
    df["q_value"] = get_q_values(df["fdr"].values)

    last_q_value = df["q_value"].iloc[-1]
    first_q_value = df["q_value"].iloc[0]

    if last_q_value <= fdr_level:
        logging.info('Last q_value {:.3f} of dataset is smaller than fdr_level {:.3f}'.format(last_q_value, fdr_level))
        cutoff_index = len(df)-1

    elif first_q_value >= fdr_level:
        logging.info('First q_value {:.3f} of dataset is larger than fdr_level {:.3f}'.format(last_q_value, fdr_level))
        cutoff_index = 0

    else:
        cutoff_index = df[df["q_value"].gt(fdr_level)].index[0] - 1

    cutoff_value = df.loc[cutoff_index]["score"]
    cutoff = df[df["score"] >= cutoff_value]

    targets = df.loc[cutoff_index, "target_cum"]
    decoy = df.loc[cutoff_index, "decoys_cum"]

    fdr = df.loc[cutoff_index, "fdr"]


    logging.info(f"{targets:,} target ({decoy:,} decoy) of {len(df)} PSMs. fdr {fdr:.6f} for a cutoff of {cutoff_value:.2f} (set fdr was {fdr_level})")

    if plot:
        import matplotlib.pyplot as plt
        import seaborn as sns
        plt.figure(figsize=(10, 5))
        plt.plot(df["score"], df["fdr"])
        plt.axhline(0.01, color="k", linestyle="--")

        plt.axvline(cutoff_value, color="r", linestyle="--")
        plt.title("fdr vs Cutoff value")
        plt.xlabel("Score")
        plt.ylabel("fdr")
        # plt.savefig('fdr.png')
        plt.show()

        bins = np.linspace(np.min(df["score"]), np.max(df["score"]), 100)
        plt.figure(figsize=(10, 5))
        sns.distplot(df[df["decoy"]]["score"].values, label="decoy", bins=bins)
        sns.distplot(df[~df["decoy"]]["score"].values, label="target", bins=bins)
        plt.xlabel("Score")
        plt.ylabel("Frequency")
        plt.title("Score vs Class")
        plt.legend()
        plt.show()

    cutoff = cutoff.reset_index(drop=True)
    return cutoff_value, cutoff

# Cell

def cut_global_fdr(data, analyte_level='sequence', fdr_level=0.01, plot=True, **kwargs):
    """
    Function to estimate and filter by global peptide or protein fdr

    """
    logging.info('Global FDR on {}'.format(analyte_level))
    data_sub = data[[analyte_level,'score','decoy']]
    data_sub_unique = data_sub.groupby([analyte_level,'decoy'], as_index=False).agg({"score": "max"})

    analyte_levels = ['precursor', 'sequence', 'protein']

    if analyte_level in analyte_levels:
        agg_score = data_sub_unique.groupby([analyte_level,'decoy'])['score'].max().reset_index()
    else:
        raise Exception('analyte_level should be either sequence or protein. The selected analyte_level was: {}'.format(analyte_level))

    agg_cval, agg_cutoff = cut_fdr(agg_score, fdr_level=fdr_level, plot=plot)

    agg_report = pd.merge(data,
                          agg_cutoff,
                          how = 'inner',
                          on = [analyte_level,'decoy'],
                          suffixes=('', '_'+analyte_level),
                          validate="many_to_one")
    return agg_report

# Cell

import networkx as nx

def get_x_tandem_score(df):

    b = df['b_hits'].astype('int').apply(lambda x: np.math.factorial(x)).values
    y = df['y_hits'].astype('int').apply(lambda x: np.math.factorial(x)).values
    x_tandem = np.log(b.astype('float')*y.astype('float')*df['matched_int'].values)

    x_tandem[x_tandem==-np.inf] = 0

    return x_tandem

def score_x_tandem(df, fdr_level = 0.01, plot = True, **kwargs):
    logging.info('Scoring using X-Tandem')
    df['score'] = get_x_tandem_score(df)
    df['decoy'] = df['sequence'].str[-1].str.islower()

    df = filter_score(df)
    df = filter_precursor(df)
    cval, cutoff = cut_fdr(df, fdr_level, plot)

    return cutoff

def filter_with_x_tandem(df, fdr_level = 0.01):
    """
    Filters a dataframe using an x_tandem score
    """
    logging.info('Filter df with x_tandem score')

    df['score'] = get_x_tandem_score(df)
    df['decoy'] = df['sequence'].str[-1].str.islower()

    df = filter_score(df)
    df = filter_precursor(df)

    return df

# Cell

def score_psms(df, score = 'y_hits', fdr_level = 0.01, plot = True, **kwargs):
    if score in df.columns:
        df['score'] = df[score]
    else:
        raise ValueError("The specified 'score' {} is not available in 'df'.".format(score))
    df['decoy'] = df['sequence'].str[-1].str.islower()

    df = filter_score(df)
    df = filter_precursor(df)
    cval, cutoff = cut_fdr(df, fdr_level, plot)

    return cutoff

# Cell

import numpy as np
import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.model_selection import GridSearchCV

import matplotlib.pyplot as plt

from .fasta import count_missed_cleavages, count_internal_cleavages


def get_ML_features(df, protease='trypsin', **kwargs):
    df['decoy'] = df['sequence'].str[-1].str.islower()

    df['abs_delta_m_ppm'] = np.abs(df['delta_m_ppm'])
    df['naked_sequence'] = df['sequence'].apply(lambda x: ''.join([_ for _ in x if _.isupper()]))
    df['n_AA']= df['naked_sequence'].str.len()
    df['matched_ion_fraction'] = df['hits']/(2*df['n_AA'])

    df['n_missed'] = df['naked_sequence'].apply(lambda x: count_missed_cleavages(x, protease))
    df['n_internal'] = df['naked_sequence'].apply(lambda x: count_internal_cleavages(x, protease))

    df['x_tandem'] = get_x_tandem_score(df)

    return df

def train_RF(df,
             exclude_features = ['precursor_idx','ion_idx','fasta_index','feature_rank','raw_rank','rank','db_idx', 'feature_idx', 'precursor', 'query_idx', 'raw_idx','sequence','decoy','naked_sequence','target'],
             train_fdr_level = 0.1,
             ini_score = 'x_tandem',
             min_train = 5000,
             test_size = 0.2,
             max_depth = [5,25,50],
             max_leaf_nodes = [150,200,250],
             n_jobs=1,
             scoring='accuracy',
             plot = False,
             random_state = 42,
             **kwargs):

    features = [_ for _ in df.columns if _ not in exclude_features]

    # Setup ML pipeline
    scaler = StandardScaler()
    rfc = RandomForestClassifier(random_state=random_state) # class_weight={False:1,True:5},
    ## Initiate scaling + classification pipeline
    pipeline = Pipeline([('scaler', scaler), ('clf', rfc)])
    parameters = {'clf__max_depth':(max_depth), 'clf__max_leaf_nodes': (max_leaf_nodes)}
    ## Setup grid search framework for parameter selection and internal cross validation
    cv = GridSearchCV(pipeline, param_grid=parameters, cv=5, scoring=scoring,
                     verbose=0,return_train_score=True,n_jobs=n_jobs)

    # Prepare target and decoy df
    df['decoy'] = df['sequence'].str[-1].str.islower()
    df['target'] = ~df['decoy']
    df['score'] = df[ini_score]
    dfT = df[~df.decoy]
    dfD = df[df.decoy]

    # Select high scoring targets (<= train_fdr_level)
    df_prescore = filter_score(df)
    df_prescore = filter_precursor(df_prescore)
    scored = cut_fdr(df_prescore, fdr_level = train_fdr_level, plot=False)[1]
    highT = scored[scored.decoy==False]
    dfT_high = dfT[dfT['query_idx'].isin(highT.query_idx)]
    dfT_high = dfT_high[dfT_high['db_idx'].isin(highT.db_idx)]

    # Determine the number of psms for semi-supervised learning
    n_train = int(dfT_high.shape[0])
    if dfD.shape[0] < n_train:
        n_train = int(dfD.shape[0])
        logging.info("The total number of available decoys is lower than the initial set of high scoring targets.")
    if n_train < min_train:
        raise ValueError("There are fewer high scoring targets or decoys than required by 'min_train'.")

    # Subset the targets and decoys datasets to result in a balanced dataset
    df_training = dfT_high.sample(n=n_train, random_state=random_state).append(dfD.sample(n=n_train, random_state=random_state))

    # Select training and test sets
    X = df_training[features]
    y = df_training['target'].astype(int)
    X_train, X_test, y_train, y_test = train_test_split(X.values, y.values, test_size=test_size, random_state=random_state, stratify=y.values)

    # Train the classifier on the training set via 5-fold cross-validation and subsequently test on the test set
    logging.info('Training & cross-validation on {} targets and {} decoys'.format(np.sum(y_train),X_train.shape[0]-np.sum(y_train)))
    cv.fit(X_train,y_train)

    logging.info('The best parameters selected by 5-fold cross-validation were {}'.format(cv.best_params_))
    logging.info('The train {} was {}'.format(scoring, cv.score(X_train, y_train)))
    logging.info('Testing on {} targets and {} decoys'.format(np.sum(y_test),X_test.shape[0]-np.sum(y_test)))
    logging.info('The test {} was {}'.format(scoring, cv.score(X_test, y_test)))

    feature_importances=cv.best_estimator_.named_steps['clf'].feature_importances_
    indices = np.argsort(feature_importances)[::-1][:40]

    top_features = X.columns[indices][:40]
    top_score = feature_importances[indices][:40]

    feature_dict = dict(zip(top_features, top_score))
    logging.info(f"Top features {feature_dict}")

    # Inspect feature importances
    if plot:
        import seaborn as sns
        g = sns.barplot(y=X.columns[indices][:40],
                        x = feature_importances[indices][:40],
                        orient='h', palette='RdBu')
        g.set_xlabel("Relative importance",fontsize=12)
        g.set_ylabel("Features",fontsize=12)
        g.tick_params(labelsize=9)
        g.set_title("Feature importance")
        plt.show()

    return cv, features

def score_ML(df,
             trained_classifier,
             features = None,
            fdr_level = 0.01,
            plot=True,
             **kwargs):

    logging.info('Scoring using Machine Learning')
    # Apply the classifier to the entire dataset
    df_new = df.copy()
    df_new['score'] = trained_classifier.predict_proba(df_new[features])[:,1]
    df_new = filter_score(df_new)
    df_new = filter_precursor(df_new)
    cval, cutoff = cut_fdr(df_new, fdr_level, plot)

    return cutoff


def filter_with_ML(df,
             trained_classifier,
             features = None,
            fdr_level = 0.01,
            plot=True,
             **kwargs):

    """
    Filters a dataframe using ML
    """
    logging.info('Filter df with x_tandem score')
    # Apply the classifier to the entire dataset
    df_new = df.copy()
    df_new['score'] = trained_classifier.predict_proba(df_new[features])[:,1]
    df_new = filter_score(df_new)
    df_new = filter_precursor(df_new)

    return df_new

# Cell
import networkx as nx

def get_unique_proteins(data, pept_dict):
    data = data.reset_index(drop=True)

    data['n_possible_proteins'] = data['sequence'].apply(lambda x: len(pept_dict[x]))
    unique_peptides = (data['n_possible_proteins'] == 1).sum()
    shared_peptides = (data['n_possible_proteins'] > 1).sum()

    logging.info(f'A total of {unique_peptides:,} unique and {shared_peptides:,} shared peptides.')

    sub = data[data['n_possible_proteins']==1]
    psms_to_protein = sub['sequence'].apply(lambda x: pept_dict[x])

    found_proteins = {}
    for idx, _ in enumerate(psms_to_protein):
        idx_ = psms_to_protein.index[idx]
        p_str = 'p' + str(_[0])
        if p_str in found_proteins:
            found_proteins[p_str] = found_proteins[p_str] + [str(idx_)]
        else:
            found_proteins[p_str] = [str(idx_)]

    #protein_count = {k:len(found_proteins[k]) for k in found_proteins.keys()}

    return data, found_proteins

def get_shared_proteins(data, found_proteins, pept_dict):

    G = nx.Graph()

    sub = data[data['n_possible_proteins']>1]

    for i in range(len(sub)):
        seq, score = sub.iloc[i][['sequence','score']]
        idx = sub.index[i]
        possible_proteins = pept_dict[seq]

        for p in possible_proteins:
            G.add_edge(str(idx), 'p'+str(p), score=score)


    connected_groups = np.array([list(c) for c in sorted(nx.connected_components(G), key=len, reverse=True)], dtype=object)
    n_groups = len(connected_groups)


    logging.info('A total of {} ambigious proteins'.format(len(connected_groups)))

    #Solving with razor:
    found_proteins_razor = {}
    for a in connected_groups:
        H = G.subgraph(a)
        shared_proteins = list(np.array(a)[np.array(list(i[0] == 'p' for i in a))])
        removed = []

        while len(shared_proteins) > 0:
            neighbors_list = []

            for node in shared_proteins:
                neighbors = list(H.neighbors(node))
                n_neigbhors = len(neighbors)

                if node in G:
                    if node in found_proteins.keys():
                        n_neigbhors+= len(found_proteins[node])

                neighbors_list.append((n_neigbhors, node, neighbors))

            neighbors_list.sort()
            #Remove the last entry:
            count, node, psms = neighbors_list[-1]
            shared_proteins.remove(node)
            psms = [_ for _ in psms if _ not in removed]
            removed += psms
            found_proteins_razor[node] = psms

    return found_proteins_razor, connected_groups



def get_protein_groups(data, pept_dict, fasta_dict, callback = None, **kwargs):
    """
    Function to perform protein grouping by razor approach
    ToDo: implement callback for solving
    Each protein is indicated with a p -> protein index
    """
    data, found_proteins = get_unique_proteins(data, pept_dict)
    found_proteins_razor, connected_groups = get_shared_proteins(data, found_proteins, pept_dict)

    report = data.copy()

    assignment = np.zeros(len(report), dtype=object)
    assignment[:] = ''
    assignment_pg = assignment.copy()
    razor = assignment.copy()
    razor[:] = False

    for protein_str in found_proteins.keys():
        protein = int(protein_str[1:])
        indexes = [int(_) for _ in found_proteins[protein_str]]
        assignment[indexes] = fasta_dict[protein]['name']
        assignment_pg[indexes] = fasta_dict[protein]['name']

    for protein_str in found_proteins_razor.keys():
        protein = int(protein_str[1:])
        indexes = [int(_) for _ in found_proteins_razor[protein_str]]
        assignment[indexes] = fasta_dict[protein]['name']
        razor[indexes] = True

    for a in connected_groups:
        protein_group = list(np.array(a)[np.array(list(i[0] == 'p' for i in a))])
        psms = [int(i) for i in a if i not in protein_group]
        assignment_pg[psms] = ','.join([fasta_dict[int(_[1:])]['name'] for _ in protein_group])

    report['protein'] = assignment
    report['protein_group'] = assignment_pg
    report['razor'] = razor

    return report

def perform_protein_grouping(data, pept_dict, fasta_dict, **kwargs):
    """
    Wrapper function to perform protein grouping by razor approach

    """
    data_sub = data[['sequence','score','decoy']]
    data_sub_unique = data_sub.groupby(['sequence','decoy'], as_index=False).agg({"score": "max"})

    targets = data_sub_unique[data_sub_unique.decoy == False]
    targets = targets.reset_index(drop=True)
    protein_targets = get_protein_groups(targets, pept_dict, fasta_dict, **kwargs)

    decoys = data_sub_unique[data_sub_unique.decoy == True]
    decoys = decoys.reset_index(drop=True)
    protein_decoys = get_protein_groups(decoys, pept_dict, fasta_dict, **kwargs)

    protein_groups = protein_targets.append(protein_decoys)
    protein_groups_app = protein_groups[['sequence','decoy','protein','protein_group','razor']]
    protein_report = pd.merge(data,
                                protein_groups_app,
                                how = 'inner',
                                on = ['sequence','decoy'],
                                validate="many_to_one")
    return protein_report

# Cell
import os
from multiprocessing import Pool

ion_dict = {}
ion_dict[0] = ''
ion_dict[1] = '-H20'
ion_dict[2] = '-NH3'

def get_ion(i, df, ions):
    start = df['ion_idx'].iloc[i]
    end = df['n_ions'].iloc[i]+start

    ion = [('b'+str(int(_))).replace('b-','y') for _ in ions.iloc[start:end]['ion_index']]
    losses = [ion_dict[int(_)] for _ in ions.iloc[start:end]['ion_type']]
    ion = [a+b for a,b in zip(ion, losses)]
    ints = ions.iloc[start:end]['ion_int'].astype('int').values

    return ion, ints


def score_hdf(to_process, callback = None, parallel=False):
    try:
        index, settings = to_process
        file_name = settings['experiment']['file_paths'][index]
        base_file_name, ext = os.path.splitext(file_name)
        ms_file = base_file_name+".ms_data.hdf"

        skip = False

        ms_file_ = alphapept.io.MS_Data_File(ms_file, is_overwritable=True)

        try:
            df = ms_file_.read(dataset_name='second_search')
            logging.info('Found second search psms for scoring.')
        except KeyError:
            try:
                df = ms_file_.read(dataset_name='first_search')
                logging.info('No second search psms for scoring found. Using first search.')
            except KeyError:
                df = pd.DataFrame()

        if len(df) == 0:
            skip = True
            logging.info('Dataframe does not contain data. Skipping scoring step.')

        if not skip:
            df = get_ML_features(df, **settings['fasta'])

            if settings["score"]["method"] == 'random_forest':
                try:
                    cv, features = train_RF(df)
                    df = filter_with_ML(df, cv, features = features, fdr_level = settings["search"]["peptide_fdr"])
                except ValueError as e:
                    logging.info('ML failed. Defaulting to x_tandem score')
                    logging.info(f"{e}")
                    df = filter_with_x_tandem(df, fdr_level = settings["search"]["peptide_fdr"])
            elif settings["score"]["method"] == 'x_tandem':
                df = filter_with_x_tandem(df, fdr_level = settings["search"]["peptide_fdr"])
            else:
                raise NotImplementedError('Scoring method {} not implemented.'.format(settings["score"]["method"]))

            df = cut_global_fdr(df, analyte_level='precursor',  plot=False, fdr_level = settings["search"]["peptide_fdr"], **settings['search'])

            logging.info('FDR on peptides complete. For {} FDR found {:,} targets and {:,} decoys.'.format(settings["search"]["peptide_fdr"], df['target'].sum(), df['decoy'].sum()) )

            # Insert here

            try:
                logging.info('Extracting ions')
                ions = ms_file_.read(dataset_name='ions')

                ion_list = []
                ion_ints = []

                for i in range(len(df)):
                    ion, ints = get_ion(i, df, ions)
                    ion_list.append(ion)
                    ion_ints.append(ints)

                df['ion_int'] = ion_ints
                df['ion_types'] = ion_list

                logging.info('Extracting ions complete.')

            except KeyError:
                logging.info('No ions present.')

            ms_file_.write(df, dataset_name="peptide_fdr")

        logging.info(f'Scoring of file {ms_file} complete.')
        return True
    except Exception as e:
        logging.error(f'Scoring of file {ms_file} failed. Exception {e}')
        return f"{e}" #Can't return exception object, cast as string

# Cell

import alphapept.utils

def protein_groups_hdf(to_process):

    skip = False
    path, pept_dict, fasta_dict, settings = to_process
    ms_file = alphapept.io.MS_Data_File(path, is_overwritable=True)
    try:
        df = ms_file.read(dataset_name='peptide_fdr')
    except KeyError:
        skip = True

    if not skip:
        df_pg = perform_protein_grouping(df, pept_dict, fasta_dict, callback = None)

        df_pg = cut_global_fdr(df_pg, analyte_level='protein',  plot=False, fdr_level = settings["search"]["protein_fdr"], **settings['search'])
        logging.info('FDR on proteins complete. For {} FDR found {:,} targets and {:,} decoys. A total of {:,} proteins found.'.format(settings["search"]["protein_fdr"], df_pg['target'].sum(), df_pg['decoy'].sum(), len(set(df_pg['protein']))))

        try:
            logging.info('Extracting ions')
            ions = ms_file.read(dataset_name='ions')

            ion_list = []
            ion_ints = []

            for i in range(len(df_pg)):
                ion, ints = get_ion(i, df_pg, ions)
                ion_list.append(ion)
                ion_ints.append(ints)

            df_pg['ion_int'] = ion_ints
            df_pg['ion_types'] = ion_list

            logging.info('Extracting ions complete.')

        except KeyError:
            logging.info('No ions present.')

        ms_file.write(df_pg, dataset_name="protein_fdr")
        base, ext = os.path.splitext(path)
        df_pg.to_csv(base+'_protein_fdr.csv')

        logging.info('Saving complete.')


def protein_grouping_all(settings, pept_dict, fasta_dict, callback=None):
    """
    Perform protein grouping on everything
    """

    df = alphapept.utils.assemble_df(settings, field = 'peptide_fdr', callback=None)

    df_pg = perform_protein_grouping(df, pept_dict, fasta_dict, callback = None)

    df_pg = cut_global_fdr(df_pg, analyte_level='protein',  plot=False, fdr_level = settings["search"]["protein_fdr"], **settings['search'])
    logging.info('FDR on proteins complete. For {} FDR found {:,} targets and {:,} decoys. A total of {:,} proteins found.'.format(settings["search"]["protein_fdr"], df_pg['target'].sum(), df_pg['decoy'].sum(), len(set(df_pg['protein']))))

    path = settings['experiment']['results_path']

    base, ext = os.path.splitext(path)

    df_pg.to_csv(base+'_protein_fdr.csv')

    df_pg.to_hdf(
        path,
        'protein_fdr'
    )

    logging.info('Saving complete.')


def protein_groups_hdf_parallel(settings, pept_dict, fasta_dict, callback=None):

    paths = []

    for _ in settings['experiment']['file_paths']:
        base, ext = os.path.splitext(_)
        hdf_path = base+'.ms_data.hdf'
        paths.append(hdf_path)

    to_process = [(path, pept_dict.copy(), fasta_dict.copy(), settings) for path in paths]

    n_processes = settings['general']['n_processes']

    if len(to_process) == 1:
        protein_groups_hdf(to_process[0])
    else:

        with Pool(n_processes) as p:
            max_ = len(to_process)
            for i, _ in enumerate(p.imap_unordered(protein_groups_hdf, to_process)):
                if callback:
                    callback((i+1)/max_)