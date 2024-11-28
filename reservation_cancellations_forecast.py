# -*- coding: utf-8 -*-
"""Reservation-Cancellations-Forecast.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/12cEg7wn02j8P_UXutGelBM-2wetal6OA
"""

# Instalar última versión de yellowbrick y sklearn
#!pip install numpy==1.20.3 pandas==1.2.4 yellowbrick==1.3.post1 scikit-learn==0.24.2 ydata-profiling

!pip install ydata-profiling

# Commented out IPython magic to ensure Python compatibility.
# Liberías estandar
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Funciones de Scikit-Learn
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import (
    RandomizedSearchCV,
    train_test_split
)

from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix
)

# Funciones de Yellow Brick
from yellowbrick.target import ClassBalance
from yellowbrick.model_selection import (ValidationCurve, FeatureImportances)
from yellowbrick.classifier.threshold import DiscriminationThreshold
from yellowbrick.classifier import (
    ConfusionMatrix,
    ClassPredictionError,
    ClassificationReport,
    PrecisionRecallCurve,
    ROCAUC,
    ClassPredictionError
)

# Importar xgboost
import xgboost as xgb

# Configurar visualizaciones
sns.set_theme(style="whitegrid")
pd.options.display.max_rows = 999
pd.options.display.max_columns = 999

# %matplotlib inline

"""## Cargar los datos

Cargamos los datos. Nuestra variable a predecir es `is_canceled`. (1) es cancelada y (0) no cancelada.
"""

# https://github.com/rfordatascience/tidytuesday/tree/master/data/2020/2020-02-11
tbl_data = (
    # Read data from the internet
    pd.read_csv("https://raw.githubusercontent.com/rfordatascience/tidytuesday/master/data/2020/2020-02-11/hotels.csv")
)

tbl_data

"""## Análisis Exploratorio de Datos (EDA)

* Aqui hay un análisis exploratorio de datos para entender los datos.
* Revísalo cuidadosamente para entender que tienen los datos.

Este reporte se construye con una librería que se llama `pandas_profiling`. Automatiza muchas gráficas y tablas resumen que se usan en los EDA.

"""

# En Google Colab ejecuta esta celda una sola vez. Después de instalar y reiniciar
# la sesión puedes comentar esta linea.
from ydata_profiling import ProfileReport
profile=ProfileReport(tbl_data, title="Pandas Profiling Report")
profile

"""## Checar el desbalance en los datos."""

(tbl_data
     .groupby(['is_canceled'])
     .size()
     .reset_index(name = 'n_reservaciones')
     .assign(pct = lambda df_: df_.n_reservaciones / df_.n_reservaciones.sum() * 100)
     .round(1)
)

fig, ax = plt.subplots(figsize = (8, 6))
sns.barplot(
    data = (tbl_data
            .groupby(['is_canceled'])
            .size()
            .reset_index(name = 'n_customers')),
    x = 'is_canceled',
    y = 'n_customers'
)
plt.title("Does customer check-in with children?")
plt.plot()

"""## Corregir desbalance con downsampling"""

def fun_downsample(tbl):
    '''
    Función para hacer downsampling
    tbl: Son los datos originales en forma de dataframe.
    '''
    # Filtramos la clase mayoritaria y sacamos de manera aleatoria N observaciones.
    # N es igual al número de observaciones en la clase minoritaria.
    # Observa que fijo una semilla en el random_state para garantizar reproducibilidad.
    tbl_reservations_not_cancelled = (
        tbl
            .query('is_canceled == 0')
            .sample(
                n = tbl.groupby(['is_canceled']).size()[1],
                random_state=42)
    )
    # Filtramos la clase minoritaria.
    tbl_reservations_cancelled = tbl.query('is_canceled == 1')

    return pd.concat([
        tbl_reservations_not_cancelled,
        tbl_reservations_cancelled
    ])

tbl_downsampled_data = fun_downsample(tbl_data)

(tbl_downsampled_data
     .groupby(['is_canceled'])
     .size()
     .reset_index(name = 'n_reservaciones')
     .assign(pct = lambda df_: df_.n_reservaciones / df_.n_reservaciones.sum() * 100)
     .round(1)
)

fig, ax = plt.subplots(figsize = (8, 6))
sns.barplot(
    data = (tbl_downsampled_data
            .groupby(['is_canceled'])
            .size()
            .reset_index(name = 'n_customers')
            .assign(is_canceled = lambda df_: df_.is_canceled.replace({0: 'not cancelled', 1: 'cancelled'}))),
    x = 'is_canceled',
    y = 'n_customers'
)
plt.title("Distribución de reservaciones con cancelaciones")
plt.show()

"""## Construimos los conjuntos de entrenamiento

"""

from sklearn.model_selection import train_test_split

y = tbl_downsampled_data.is_canceled
X = tbl_downsampled_data.drop(columns = 'is_canceled')

X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=0.2,
    random_state=42
)

print(f'X_train shape: {X_train.shape}')
print(f'y_train shape: {y_train.shape}')

print(f'X_test shape: {X_test.shape}')
print(f'y_test shape: {y_test.shape}')

from sklearn.preprocessing import OneHotEncoder

variable_selection_numeric = ['OverallQual', 'GrLivArea', 'YearBuilt', '1stFlrSF']
variable_selection_categoric = ['Neighborhood','MSZoning']               # <--- Selecciona las variable categóricas

def prep_for_ml(tbl_train, tbl_test):
    '''Clean X_train and X_test
        1) Select continuous and categorical variables.
        2) Convert categorical variables to one hot encoding
        3) Concatenate clean dataframes
    '''
    # Continuous variables
    tbl_num_train = tbl_train.loc[:, variable_selection_numeric]
    tbl_num_test = tbl_test.loc[:, variable_selection_numeric]

    # Categorical variables
    tbl_cat_train = tbl_train.loc[:, variable_selection_categoric]
    tbl_cat_test = tbl_test.loc[:, variable_selection_categoric]

    ohe = OneHotEncoder(drop = 'first', sparse = False)
    ohe.fit(tbl_cat_train)
    col_names = ohe.get_feature_names_out()

    tbl_ohe_cat_train = pd.DataFrame(
        ohe.transform( tbl_cat_train )
    )

    tbl_ohe_cat_test = pd.DataFrame(
        ohe.transform( tbl_cat_test )
    )
    # Add new column names
    tbl_ohe_cat_train.columns = col_names
    tbl_ohe_cat_test.columns = col_names

    # Join transformed continuous + categorical variables
    tbl_train_clean = pd.concat([tbl_num_train.reset_index(drop = True), tbl_ohe_cat_train], axis = 1)
    tbl_test_clean = pd.concat([tbl_num_test.reset_index(drop = True), tbl_ohe_cat_test], axis = 1)

    return (tbl_train_clean, tbl_test_clean)

X_train_clean, X_test_clean = prep_for_ml(X_train, X_test)

assert fun_preprocesar_atributos(train_set).columns.tolist() == fun_preprocesar_atributos(test_set).columns.tolist()