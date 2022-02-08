# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/06_score.ipynb (unless otherwise specified).

__all__ = ['filter_score', 'filter_precursor', 'get_q_values', 'cut_fdr', 'cut_global_fdr', 'get_x_tandem_score',
           'score_x_tandem', 'filter_with_x_tandem', 'filter_with_score', 'score_psms', 'get_ML_features', 'train_RF',
           'score_ML', 'filter_with_ML', 'assign_proteins', 'get_shared_proteins', 'get_protein_groups',
           'perform_protein_grouping', 'get_ion', 'ion_dict', 'ecdf', 'score_hdf', 'protein_grouping_all']

# Cell
import numpy as np
import pandas as pd
import logging
import alphapept.io

def filter_score(df: pd.DataFrame, mode: str='multiple') -> pd.DataFrame:
    """
    Filter psms feature table by keeping only the best scoring psm per experimental spectrum.

    TODO: psms could still have the same score when having modifications at multiple positions that are not distinguishable.
    Only keep one.

    Args:
        df (pd.DataFrame): psms table of search results from alphapept.
        mode (str, optional): string specifying which mode to use for psms filtering. The two options are 'single' and 'multiple'. 'single' will only keep one feature per experimental spectrum. 'multiple' will allow multiple features per experimental spectrum. In either option, each feature can only occur once. Defaults to 'multiple'.

    Returns:
        pd.DataFrame: table containing the filtered psms results.
    """

    if "localexp" in df.columns:
        additional_group = ['localexp']
    else:
        additional_group = []

    df["rank"] = df.groupby(["query_idx"] + additional_group)["score"].rank("dense", ascending=False).astype("int")
    df = df[df["rank"] == 1]

    # in case two hits have the same score and therfore the same rank only accept the first one
    df = df.drop_duplicates(["query_idx"] + additional_group)

    if 'dist' in df.columns:
        df["feature_rank"] = df.groupby(["feature_idx"] + additional_group)["dist"].rank("dense", ascending=True).astype("int")
        df["raw_rank"] = df.groupby(["raw_idx"] + additional_group)["score"].rank("dense", ascending=False).astype("int")

        if mode == 'single':
            df_filtered = df[(df["feature_rank"] == 1) & (df["raw_rank"] == 1) ]
            df_filtered = df_filtered.drop_duplicates(["raw_idx"] + additional_group)

        elif mode == 'multiple':
            df_filtered = df[(df["feature_rank"] == 1)]

        else:
            raise NotImplementedError('Mode {} not implemented yet'.format(mode))

    else:
        df_filtered = df

    # TOD: this needs to be sorted out, for modifications -> What if we have MoxM -> oxMM, this will screw up with the filter sequence part
    return df_filtered

# Cell

def filter_precursor(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter psms feature table by precursor.
    Allow each precursor only once.

    Args:
        df (pd.DataFrame): psms table of search results from alphapept.

    Returns:
        pd.DataFrame: table containing the filtered psms results.

    """
    if "localexp" in df.columns:
        additional_group = ['localexp']
    else:
        additional_group = []

    df["rank_precursor"] = (
        df.groupby(["precursor"] + additional_group)["score"].rank("dense", ascending=False).astype("int")
    )

    df_filtered = df[df["rank_precursor"] == 1]

    if 'int_sum' in df_filtered.columns:
        #if int_sum from feature finding is present: Remove duplicates in case there are any
        df_filtered = df_filtered.sort_values('int_sum')[::-1]
        df_filtered = df_filtered.drop_duplicates(["precursor", "rank_precursor"] + additional_group)

    return df_filtered

# Cell
from numba import njit
@njit
def get_q_values(fdr_values: np.ndarray) -> np.ndarray:
    """
    Calculate q-values from fdr_values.

    Args:
        fdr_values (np.ndarray): np.ndarray of fdr values.

    Returns:
        np.ndarray: np.ndarray of q-values.
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

#Note that the test function for cut_fdr is further down in the notebook to also test protein-level FDR.
def cut_fdr(df: pd.DataFrame, fdr_level:float=0.01, plot:bool=True) -> (float, pd.DataFrame):
    """
    Cuts a dataframe with a given fdr level

    Args:
        df (pd.DataFrame): psms table of search results from alphapept.
        fdr_level (float, optional): fdr level that should be used for filtering. The value should lie between 0 and 1. Defaults to 0.01.
        plot (bool, optional): flag to enable plot. Defaults to 'True'.

    Returns:
        float: numerical value of the applied score cutoff
        pd.DataFrame: df with psms within fdr

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
        plt.hist(df[df["decoy"]]["score"].values, label="decoy", bins=bins, alpha=0.5)
        plt.hist(df[~df["decoy"]]["score"].values, label="target", bins=bins, alpha=0.5)
        plt.xlabel("Score")
        plt.ylabel("Frequency")
        plt.title("Score vs Class")
        plt.legend()
        plt.show()

    cutoff = cutoff.reset_index(drop=True)
    return cutoff_value, cutoff

# Cell

def cut_global_fdr(data: pd.DataFrame, analyte_level: str='sequence', fdr_level: float=0.01, plot: bool=True, **kwargs) -> pd.DataFrame:
    """
    Function to estimate and filter by global peptide or protein fdr

    Args:
        data (pd.DataFrame): psms table of search results from alphapept.
        analyte_level (str, optional): string specifying the analyte level to apply the fdr threshold. Options include: 'precursor', 'sequence', 'protein_group' and 'protein'. Defaults to 'sequence'.
        fdr_level (float, optional): fdr level that should be used for filtering. The value should lie between 0 and 1. Defaults to 0.01.
        plot (bool, optional): flag to enable plot. Defaults to 'True'.

    Returns:
        pd.DataFrame: df with filtered results

    """
    logging.info('Global FDR on {}'.format(analyte_level))
    data_sub = data[[analyte_level,'score','decoy']]
    data_sub_unique = data_sub.groupby([analyte_level,'decoy'], as_index=False).agg({"score": "max"})

    analyte_levels = ['precursor', 'sequence', 'protein_group','protein']

    if analyte_level in analyte_levels:
        agg_score = data_sub_unique.groupby([analyte_level,'decoy'])['score'].max().reset_index()
    else:
        raise Exception('analyte_level should be either sequence or protein. The selected analyte_level was: {}'.format(analyte_level))

    agg_cval, agg_cutoff = cut_fdr(agg_score, fdr_level=fdr_level, plot=plot)

    agg_report = data.reset_index().merge(
                        agg_cutoff,
                        how = 'inner',
                        on = [analyte_level,'decoy'],
                        suffixes=('', '_'+analyte_level),
                        validate="many_to_one").set_index('index') #retain the original index
    return agg_report

# Cell

import networkx as nx

def get_x_tandem_score(df: pd.DataFrame) -> np.ndarray:
    """
    Function to calculate the x tandem score

    Args:
        df (pd.DataFrame): psms table of search results from alphapept.

    Returns:
        np.ndarray: np.ndarray with x_tandem scores

    """
    b = df['b_hits'].astype('int').apply(lambda x: np.math.factorial(x)).values
    y = df['y_hits'].astype('int').apply(lambda x: np.math.factorial(x)).values
    x_tandem = np.log(b.astype('float')*y.astype('float')*df['matched_int'].values)

    x_tandem[x_tandem==-np.inf] = 0

    return x_tandem

def score_x_tandem(df: pd.DataFrame, fdr_level: float = 0.01, plot: bool = True, **kwargs) -> pd.DataFrame:
    """
    Filters the psms table by using the x_tandem score and filtering the results for fdr_level.

    Args:
        df (pd.DataFrame): psms table of search results from alphapept.
        fdr_level (float, optional): fdr level that should be used for filtering. The value should lie between 0 and 1. Defaults to 0.01.

    Returns:
        pd.DataFrame: psms table with an extra 'score' column for x_tandem, filtered for no feature or precursor to be assigned multiple times.
    """
    logging.info('Scoring using X-Tandem')
    if 'localexp' not in df.columns:
        df['localexp'] = 0
    df['score'] = get_x_tandem_score(df)
    df['decoy'] = df['sequence'].str[-1].str.islower()

    df = filter_score(df)
    df = filter_precursor(df)
    cval, cutoff = cut_fdr(df, fdr_level, plot)

    return cutoff

def filter_with_x_tandem(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filters the psms table by using the x_tandem score, no fdr filter.
    TODO: Remove redundancy with score functions, see issue: #275

    Args:
        df (pd.DataFrame): psms table of search results from alphapept.

    Returns:
        pd.DataFrame: psms table with an extra 'score' column for x_tandem, filtered for no feature or precursor to be assigned multiple times.
    """
    logging.info('Filter df with x_tandem score')

    df['score'] = get_x_tandem_score(df)
    df['decoy'] = df['sequence'].str[-1].str.islower()

    df = filter_score(df)
    df = filter_precursor(df)

    return df

def filter_with_score(df: pd.DataFrame):
    """
    Filters the psms table by using the score column, no fdr filter.
    TODO: Remove redundancy with score functions, see issue: #275

    Args:
        df (pd.DataFrame): psms table of search results from alphapept.

    Returns:
        pd.DataFrame: psms table filtered for no feature or precursor to be assigned multiple times.
    """
    logging.info('Filter df with custom score')

    df['decoy'] = df['sequence'].str[-1].str.islower()

    df = filter_score(df)
    df = filter_precursor(df)

    return df

# Cell

def score_psms(df: pd.DataFrame, score: str='y_hits', fdr_level: float=0.01, plot: bool=True, **kwargs) -> pd.DataFrame:
    """
    Uses the specified score in df to filter psms and to apply the fdr_level threshold.

    Args:
        df (pd.DataFrame): psms table of search results from alphapept.
        score (str, optional): string specifying the column in df to use as score. Defaults to 'y_hits'.
        fdr_level (float, optional): fdr level that should be used for filtering. The value should lie between 0 and 1. Defaults to 0.01.
        plot (bool, optional): flag to enable plot. Defaults to 'True'.

    Returns:
        pd.DataFrame: filtered df with psms within fdr

    """
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
import sys

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.model_selection import GridSearchCV

import matplotlib.pyplot as plt

from .fasta import count_missed_cleavages, count_internal_cleavages


def get_ML_features(df: pd.DataFrame, protease: str='trypsin', **kwargs) -> pd.DataFrame:
    """
    Uses the specified score in df to filter psms and to apply the fdr_level threshold.

    Args:
        df (pd.DataFrame): psms table of search results from alphapept.
        protease (str, optional): string specifying the protease that was used for proteolytic digestion. Defaults to 'trypsin'.

    Returns:
        pd.DataFrame: df including additional scores for subsequent ML.

    """
    df['decoy'] = df['sequence'].str[-1].str.islower()

    df['abs_delta_m_ppm'] = np.abs(df['delta_m_ppm'])
    df['naked_sequence'] = df['sequence'].apply(lambda x: ''.join([_ for _ in x if _.isupper()]))
    df['n_AA']= df['naked_sequence'].str.len()
    df['matched_ion_fraction'] = df['hits']/(2*df['n_AA'])

    df['n_missed'] = df['naked_sequence'].apply(lambda x: count_missed_cleavages(x, protease))
    df['n_internal'] = df['naked_sequence'].apply(lambda x: count_internal_cleavages(x, protease))

    df['x_tandem'] = get_x_tandem_score(df)

    return df

def train_RF(df: pd.DataFrame,
             exclude_features: list = ['precursor_idx','ion_idx','fasta_index','feature_rank','raw_rank','rank','db_idx', 'feature_idx', 'precursor', 'query_idx', 'raw_idx','sequence','decoy','naked_sequence','target'],
             train_fdr_level:  float = 0.1,
             ini_score: str = 'x_tandem',
             min_train: int = 1000,
             test_size: float = 0.8,
             max_depth: list = [5,25,50],
             max_leaf_nodes: list = [150,200,250],
             n_jobs: int = -1,
             scoring: str = 'accuracy',
             plot:bool = False,
             random_state: int = 42,
             **kwargs) -> (GridSearchCV, list):

    """
    Function to train a random forest classifier to separate targets from decoys via semi-supervised learning.

    Args:
        df (pd.DataFrame): psms table of search results from alphapept.
        exclude_features (list, optional): list with features to exclude for ML. Defaults to ['precursor_idx','ion_idx','fasta_index','feature_rank','raw_rank','rank','db_idx', 'feature_idx', 'precursor', 'query_idx', 'raw_idx','sequence','decoy','naked_sequence','target'].
        train_fdr_level (float, optional): Only targets below the train_fdr_level cutoff are considered for training the classifier. Defaults to 0.1.
        ini_score (str, optional): Initial score to select psms set for semi-supervised learning. Defaults to 'x_tandem'.
        min_train (int, optional): Minimum number of psms in the training set. Defaults to 1000.
        test_size (float, optional): Fraction of psms used for testing. Defaults to 0.8.
        max_depth (list, optional): List of clf__max_depth parameters to test in the grid search. Defaults to [5,25,50].
        max_leaf_nodes (list, optional): List of clf__max_leaf_nodes parameters to test in the grid search. Defaults to [150,200,250].
        n_jobs (int, optional): Number of jobs to use for parallelizing the gridsearch. Defaults to -1.
        scoring (str, optional): Scoring method for the gridsearch. Defaults to'accuracy'.
        plot (bool, optional): flag to enable plot. Defaults to 'False'.
        random_state (int, optional): Random state for initializing the RandomForestClassifier. Defaults to 42.

    Returns:
        [GridSearchCV, list]: GridSearchCV: GridSearchCV object with trained RandomForestClassifier. list: list of features used for training the classifier.

    """

    if getattr(sys, 'frozen', False):
        logging.info('Using frozen pyinstaller version. Setting n_jobs to 1')
        n_jobs = 1

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

def score_ML(df: pd.DataFrame,
             trained_classifier: GridSearchCV,
             features: list = None,
             fdr_level: float = 0.01,
             plot: bool = True,
             **kwargs) -> pd.DataFrame:
    """
    Applies a trained ML classifier to df and uses the ML score to filter psms and to apply the fdr_level threshold.

    Args:
        df (pd.DataFrame): psms table of search results from alphapept.
        trained_classifier (GridSearchCV): GridSearchCV object returned by train_RF.
        features (list): list with features returned by train_RF. Defaults to 'None'.
        fdr_level (float, optional): fdr level that should be used for filtering. The value should lie between 0 and 1. Defaults to 0.01.
        plot (bool, optional): flag to enable plot. Defaults to 'True'.

    Returns:
        pd.DataFrame: filtered df with psms within fdr

    """
    logging.info('Scoring using Machine Learning')
    # Apply the classifier to the entire dataset
    df_new = df.copy()
    df_new['score'] = trained_classifier.predict_proba(df_new[features])[:,1]
    df_new = filter_score(df_new)
    df_new = filter_precursor(df_new)
    cval, cutoff = cut_fdr(df_new, fdr_level, plot)

    return cutoff


def filter_with_ML(df: pd.DataFrame,
             trained_classifier: GridSearchCV,
             features: list = None,
             **kwargs) -> pd.DataFrame:

    """
    Filters the psms table by using the x_tandem score, no fdr filter.
    TODO: Remove redundancy with score functions, see issue: #275

    Args:
        df (pd.DataFrame): psms table of search results from alphapept.
        trained_classifier (GridSearchCV): GridSearchCV object returned by train_RF.
        features (list): list with features returned by train_RF. Defaults to 'None'.

    Returns:
        pd.DataFrame: psms table with an extra 'score' column from the trained_classifier by ML, filtered for no feature or precursor to be assigned multiple times.
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

def assign_proteins(data: pd.DataFrame, pept_dict: dict) -> (pd.DataFrame, dict):
    """
    Assign psms to proteins.
    This function appends the dataframe with a column 'n_possible_proteins' which indicates how many proteins a psm could be matched to.
    It returns the appended dataframe and a dictionary `found_proteins` where each protein is mapped to the psms indices.

    Args:
        data (pd.DataFrame): psms table of scored and filtered search results from alphapept.
        pept_dict (dict): dictionary that matches peptide sequences to proteins

    Returns:
        pd.DataFrame: psms table of search results from alphapept appended with the number of matched proteins.
        dict: dictionary mapping psms indices to proteins.

    """

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

    return data, found_proteins

def get_shared_proteins(data: pd.DataFrame, found_proteins: dict, pept_dict: dict) -> dict:
    """
    Assign peptides to razor proteins.

    Args:
        data (pd.DataFrame): psms table of scored and filtered search results from alphapept, appended with `n_possible_proteins`.
        found_proteins (dict): dictionary mapping psms indices to proteins
        pept_dict (dict): dictionary mapping peptide indices to the originating proteins as a list

    Returns:
        dict: dictionary mapping peptides to razor proteins

    """

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
    for a in connected_groups[::-1]:
        H = G.subgraph(a).copy()
        shared_proteins = list(np.array(a)[np.array(list(i[0] == 'p' for i in a))])

        while len(shared_proteins) > 0:
            neighbors_list = []

            for node in shared_proteins:
                shared_peptides = list(H.neighbors(node))

                if node in G:
                    if node in found_proteins.keys():
                        shared_peptides += found_proteins[node]

                n_neigbhors = len(shared_peptides)

                neighbors_list.append((n_neigbhors, node, shared_peptides))


            #Check if we have a protein_group (e.g. they share the same everythin)
            neighbors_list.sort()

            # Check for protein group
            node_ = [neighbors_list[-1][1]]
            idx = 1
            while idx < len(neighbors_list): #Check for protein groups
                if neighbors_list[-idx][0] == neighbors_list[-idx-1][0]: #lenght check
                    if set(neighbors_list[-idx][2]) == set(neighbors_list[-idx-1][2]): #identical peptides
                        node_.append(neighbors_list[-idx-1][1])
                        idx += 1
                    else:
                        break
                else:
                    break

            #Remove the last entry:
            shared_peptides = neighbors_list[-1][2]
            for node in node_:
                shared_proteins.remove(node)

            for _ in shared_peptides:
                if _ in H:
                    H.remove_node(_)

            if len(shared_peptides) > 0:
                if len(node_) > 1:
                    node_ = tuple(node_)
                else:
                    node_ = node_[0]

                found_proteins_razor[node_] = shared_peptides

    return found_proteins_razor



def get_protein_groups(data: pd.DataFrame, pept_dict: dict, fasta_dict: dict, decoy = False, callback = None, **kwargs) -> pd.DataFrame:
    """
    Function to perform protein grouping by razor approach.
    This function calls `assign_proteins` and `get_shared_proteins`.
    ToDo: implement callback for solving
    Each protein is indicated with a p -> protein index

    Args:
        data (pd.DataFrame): psms table of scored and filtered search results from alphapept.
        pept_dict (dict): A dictionary mapping peptide indices to the originating proteins as a list.
        fasta_dict (dict): A dictionary with fasta sequences.
        decoy (bool, optional): Defaults to False.
        callback (bool, optional): Defaults to None.

    Returns:
        pd.DataFrame: alphapept results table now including protein level information.
    """
    data, found_proteins = assign_proteins(data, pept_dict)
    found_proteins_razor = get_shared_proteins(data, found_proteins, pept_dict)

    report = data.copy()

    assignment = np.zeros(len(report), dtype=object)
    assignment[:] = ''
    assignment_pg = assignment.copy()

    assignment_idx = assignment.copy()
    assignment_idx[:] = ''

    razor = assignment.copy()
    razor[:] = False

    if decoy:
        add = 'REV__'
    else:
        add = ''

    for protein_str in found_proteins.keys():
        protein = int(protein_str[1:])
        protein_name = add+fasta_dict[protein]['name']
        indexes = [int(_) for _ in found_proteins[protein_str]]
        assignment[indexes] = protein_name
        assignment_pg[indexes] = protein_name
        assignment_idx[indexes] = str(protein)

    for protein_str in found_proteins_razor.keys():
        indexes = [int(_) for _ in found_proteins_razor[protein_str]]

        if isinstance(protein_str, tuple):
            proteins = [int(_[1:]) for _ in protein_str]
            protein_name = ','.join([add+fasta_dict[_]['name'] for _ in proteins])
            protein = ','.join([str(_) for _ in proteins])

        else:
            protein = int(protein_str[1:])
            protein_name = add+fasta_dict[protein]['name']

        assignment[indexes] = protein_name
        assignment_pg[indexes] = protein_name
        assignment_idx[indexes] = str(protein)
        razor[indexes] = True

    report['protein'] = assignment
    report['protein_group'] = assignment_pg
    report['razor'] = razor
    report['protein_idx'] = assignment_idx

    return report

def perform_protein_grouping(data: pd.DataFrame, pept_dict: dict, fasta_dict: dict, **kwargs) -> pd.DataFrame:
    """
    Wrapper function to perform protein grouping by razor approach

    Args:
        data (pd.DataFrame): psms table of scored and filtered search results from alphapept.
        pept_dict (dict): A dictionary mapping peptide indices to the originating proteins as a list.
        fasta_dict (dict): A dictionary with fasta sequences.

    Returns:
        pd.DataFrame: alphapept results table now including protein level information.
    """
    data_sub = data[['sequence','score','decoy']]
    data_sub_unique = data_sub.groupby(['sequence','decoy'], as_index=False).agg({"score": "max"})

    targets = data_sub_unique[data_sub_unique.decoy == False]
    targets = targets.reset_index(drop=True)
    protein_targets = get_protein_groups(targets, pept_dict, fasta_dict, **kwargs)

    protein_targets['decoy_protein'] = False

    decoys = data_sub_unique[data_sub_unique.decoy == True]
    decoys = decoys.reset_index(drop=True)
    protein_decoys = get_protein_groups(decoys, pept_dict, fasta_dict, decoy=True, **kwargs)

    protein_decoys['decoy_protein'] = True

    protein_groups = protein_targets.append(protein_decoys)
    protein_groups_app = protein_groups[['sequence','decoy','protein','protein_group','razor','protein_idx','decoy_protein','n_possible_proteins']]
    protein_report = pd.merge(data,
                                protein_groups_app,
                                how = 'inner',
                                on = ['sequence','decoy'],
                                validate="many_to_one")


    return protein_report

# Cell

ion_dict = {}
ion_dict[0] = ''
ion_dict[1] = '-H20'
ion_dict[2] = '-NH3'

def get_ion(i: int, df: pd.DataFrame, ions: pd.DataFrame)-> (list, np.ndarray):
    """
    Helper function to extract the ion-hits for a given DataFrame index.
    This function extracts the hit type and the intensities.
    E.g.: ['b1','y1'], np.array([10,20]).

    Args:
        i (int): Row index for the DataFrame
        df (pd.DataFrame): DataFrame with PSMs
        ions (pd.DataFrame): DataFrame with ion hits

    Returns:
        list: List with strings that describe the ion type.
        np.ndarray: Array with intensity information
    """
    start = df['ion_idx'].iloc[i]
    end = df['n_ions'].iloc[i]+start

    ion = [('b'+str(int(_))).replace('b-','y') for _ in ions.iloc[start:end]['ion_index']]
    losses = [ion_dict[int(_)] for _ in ions.iloc[start:end]['ion_type']]
    ion = [a+b for a,b in zip(ion, losses)]
    ints = ions.iloc[start:end]['ion_int'].astype('int').values

    return ion, ints

# Cell
def ecdf(data:np.ndarray)-> (np.ndarray, np.ndarray):
    """Compute ECDF.
    Helper function to calculate the ECDF of a score distribution.
    This is later used to normalize the score from an arbitrary range to [0,1].

    Args:
        data (np.ndarray): Array containting the score.

    Returns:
        np.ndarray: Array containg the score, sorted.
        np.ndarray: Noramalized counts.

    """
    x = np.sort(data)
    n = x.size
    y = np.arange(1, n+1) / n

    return (x,y)

# Cell
import os
from multiprocessing import Pool
from scipy.interpolate import interp1d
from typing import Callable, Union

#This function has no unit test and is covered by the quick_test
def score_hdf(to_process: tuple, callback: Callable = None, parallel: bool=False) -> Union[bool, str]:
    """Apply scoring on an hdf file to be called from a parallel pool.
    This function does not raise errors but returns the exception as a string.
    Args:
        to_process: (int, dict): Tuple containg a file index and the settings.
        callback: (Callable): Optional callback
        parallel: (bool): Parallel flag (unused).

    Returns:
        Union[bool, str]: True if no eo exception occured, the exception if things failed.

    """

    logging.info('Calling score_hdf')

    index, settings = to_process

    try:
        #This part collects all ms_data files that belong to one sample.
        exp_name = sorted(settings['experiment']['fraction_dict'].keys())[index]
        shortnames = settings['experiment']['fraction_dict'].get(exp_name)
        file_paths = settings['experiment']['file_paths']
        relevant_files = []
        for shortname in shortnames:
            for file_path in file_paths:
                if shortname in file_path:
                    relevant_files.append(file_path)
                    break

        ms_file_names = [os.path.splitext(x)[0]+".ms_data.hdf" for x in relevant_files]
        skip = False

        all_dfs = []
        ms_file2idx = {}
        idx_start = 0
        for ms_filename in ms_file_names:
            ms_file_ = alphapept.io.MS_Data_File(ms_filename, is_overwritable=True)

            try:
                df = ms_file_.read(dataset_name='second_search')
                logging.info('Found second search psms for scoring.')
            except KeyError:
                try:
                    df = ms_file_.read(dataset_name='first_search')
                    logging.info('No second search psms for scoring found. Using first search.')
                except KeyError:
                    df = pd.DataFrame()
            df["localexp"] = idx_start


            df.index = df.index+idx_start
            ms_file2idx[ms_file_] = df.index
            all_dfs.append(df)
            idx_start+=len(df.index)

        df = pd.concat(all_dfs)


        if len(df) == 0:
            skip = True
            logging.info('Dataframe does not contain data. Skipping scoring step.')

        if not skip:
            df_ = get_ML_features(df, **settings['fasta'])

            if settings["score"]["method"] == 'random_forest':
                try:
                    cv, features = train_RF(df)
                    df = filter_with_ML(df_, cv, features = features)
                except ValueError as e:
                    logging.info('ML failed. Defaulting to x_tandem score')
                    logging.info(f"{e}")

                    logging.info('Converting x_tandem score to probabilities')

                    x_, y_ = ecdf(df_['score'].values)
                    f = interp1d(x_, y_, bounds_error = False, fill_value=(y_.min(), y_.max()))

                    df_['score'] = df_['score'].apply(lambda x: f(x))
                    df = filter_with_score(df_)

            elif settings["score"]["method"] == 'x_tandem':
                df = filter_with_x_tandem(df)
            else:
                try:
                    import importlib
                    alphapept_plugin = importlib.import_module(settings["score"]["method"]+".alphapept_plugin")
                    df = alphapept_plugin.score_alphapept(df, index, settings)
                except Exception as e:
                    raise NotImplementedError('Scoring method {} not implemented. Other exception info: {}'.format(settings["score"]["method"], e))

            df_pfdr = cut_global_fdr(df, analyte_level='precursor',  plot=False, fdr_level = settings["search"]["peptide_fdr"], **settings['search'])

            logging.info('FDR on peptides complete. For {} FDR found {:,} targets and {:,} decoys.'.format(settings["search"]["peptide_fdr"], df['target'].sum(), df['decoy'].sum()) )

            for ms_file_, idxs in ms_file2idx.items():
                df_file = df.loc[df.index.intersection(idxs)]
                try:
                    logging.info('Extracting ions')
                    ions = ms_file_.read(dataset_name='ions')

                    ion_list = []
                    ion_ints = []

                    for i in range(len(df_file)):
                        ion, ints = get_ion(i, df_file, ions)
                        ion_list.append(ion)
                        ion_ints.append(ints)

                    df_file['ion_int'] = ion_ints
                    df_file['ion_types'] = ion_list


                    logging.info('Extracting ions complete.')

                except KeyError:
                    logging.info('No ions present.')

            export_df = df_file.reset_index().drop(columns=['localexp'])
            if 'level_0' in export_df.columns:
                export_df = export_df.drop(columns = ['level_0'])

            ms_file_.write(export_df, dataset_name="peptide_fdr")

            logging.info(f'Scoring of files {list(ms_file2idx.keys())} complete.')
        return True
    except Exception as e:
        logging.info(f'Scoring of file {index} failed. Exception {e}')
        return f"{e}" #Can't return exception object, cast as string


import alphapept.utils

#This function has no unit test and is covered by the quick_test
def protein_grouping_all(settings:dict, pept_dict:dict, fasta_dict:dict, callback=None):
    """Apply protein grouping on all files in an experiment.
    This function will load all dataframes (peptide_fdr level) and perform protein grouping.

    Args:
        settings: (dict): Settings file for the experiment
        pept_dict: (dict): A peptide dictionary.
        fast_dict: (dict): A FASTA dictionary.
        callback: (Callable): Optional callback.
    """

    df = alphapept.utils.assemble_df(settings, field = 'peptide_fdr', callback=None)
    if len(df) > 0:
        df_pg = perform_protein_grouping(df, pept_dict, fasta_dict, callback = None)

        df_pg = cut_global_fdr(df_pg, analyte_level='protein_group',  plot=False, fdr_level = settings["search"]["protein_fdr"], **settings['search'])
        logging.info('FDR on proteins complete. For {} FDR found {:,} targets and {:,} decoys. A total of {:,} proteins found.'.format(settings["search"]["protein_fdr"], df_pg['target'].sum(), df_pg['decoy'].sum(), len(set(df_pg['protein']))))

        path = settings['experiment']['results_path']

        base, ext = os.path.splitext(path)

        df_pg.to_hdf(
            path,
            'protein_fdr'
        )

        logging.info('Saving complete.')

    else:
        logging.info('No peptides for grouping present. Skipping.')