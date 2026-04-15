import tensorflow as tf
import numpy as np
import xgboost as xgb

print(f"Python     : {__import__('sys').version.split()[0]}")
print(f"NumPy      : {np.__version__}")
print(f"TensorFlow : {tf.__version__}")
print(f"XGBoost    : {xgb.__version__}")

gpus = tf.config.list_physical_devices('GPU')
print(f"\nGPUs found : {len(gpus)}")
for g in gpus:
    print(f"  {g}")

if gpus:
    # Quick matrix multiply on GPU
    with tf.device('/GPU:0'):
        a = tf.constant([[1.0, 2.0], [3.0, 4.0]])
        b = tf.constant([[5.0, 6.0], [7.0, 8.0]])
        c = tf.matmul(a, b)
    print(f"\nGPU matmul result:\n{c.numpy()}")
    print("\n✅ GPU is working correctly!")
else:
    print("\n⚠ No GPU found — TF will run on CPU only.")
    print("  Check CUDA PATH and cuDNN DLL placement.")

# XGBoost GPU check
try:
    import numpy as np
    dtrain = xgb.DMatrix(np.random.rand(100, 10), label=np.random.randint(0, 2, 100))
    params = {'tree_method': 'hist', 'device': 'cuda', 'verbosity': 0}
    xgb.train(params, dtrain, num_boost_round=1)
    print("✅ XGBoost GPU working!")
except Exception as e:
    print(f"⚠ XGBoost GPU not available: {e}")
    print("  XGBoost will fall back to CPU automatically.")