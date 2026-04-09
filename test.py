import tensorflow as tf

import numpy as np
import xgboost as xgb
gpus = tf.config.list_physical_devices('GPU')
if gpus:
    try:
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)
        print(f'[GPU] TensorFlow detected {len(gpus)} GPU(s): {[g.name for g in gpus]}')
        print('[GPU] Memory-growth enabled — TF will use GPU for LSTM training.')
    except RuntimeError as e:
        print(f'[GPU] Memory-growth config error: {e}')
else:
    print('[GPU] No GPU detected by TensorFlow — LSTM will run on CPU.')

# XGBoost GPU device string (used later when building the model)
# 'cuda' for XGBoost >= 2.0 ;  older versions used 'gpu_hist'
try:
    _xgb_ver = tuple(int(x) for x in xgb.__version__.split('.')[:2])
    XGB_DEVICE = 'cuda' if _xgb_ver >= (2, 0) else 'gpu_hist'
    XGB_TREE_METHOD = 'hist'           # 'hist' works for both CPU and GPU in XGB>=2
except Exception:
    XGB_DEVICE = 'cpu'
    XGB_TREE_METHOD = 'hist'

# Detect if an NVIDIA GPU is actually available for XGBoost
try:
    _test_dmat = xgb.DMatrix(np.zeros((2, 2)), label=np.zeros(2))
    _test_params = {'tree_method': XGB_TREE_METHOD, 'device': XGB_DEVICE,
                    'n_estimators': 1, 'verbosity': 0}
    xgb.train(_test_params, _test_dmat, num_boost_round=1)
    print(f'[GPU] XGBoost GPU ({XGB_DEVICE}) confirmed available.')
except Exception:
    XGB_DEVICE = 'cpu'
    print('[GPU] XGBoost GPU not available — will use CPU.')

# import tensorflow as tf
# print("TF version:", tf.__version__)
# print("Built with CUDA:", tf.test.is_built_with_cuda())
# print("GPU:", tf.config.list_physical_devices('GPU'))