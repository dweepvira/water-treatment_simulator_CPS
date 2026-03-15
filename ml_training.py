#!/usr/bin/env python3
"""
Enhanced Multi-Class ML Training for SWAT
==========================================
Models optimized for multi-class attack detection:
- Random Forest (ensemble)
- XGBoost (gradient boosting)
- LightGBM (fast gradient boosting)
- LSTM (temporal patterns)
- Stacking ensemble (combines all)

NO one-class SVM (wrong for multi-class problem)
"""

import numpy as np
import pandas as pd
from pathlib import Path
import joblib
import json
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.metrics import (classification_report, confusion_matrix, 
                            accuracy_score, f1_score, precision_score, recall_score)
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from sklearn.preprocessing import LabelEncoder
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
warnings.filterwarnings('ignore')


class SWATMultiClassTrainer:
    """Train and evaluate multi-class attack detection models."""
    
    def __init__(self, data_dir='ml_ready', output_dir='trained_models'):
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.models = {}
        self.results = {}
        self.best_model = None
        self.best_score = 0
        
    def load_data(self):
        """Load preprocessed features."""
        print("Loading data...")
        
        X = pd.read_csv(self.data_dir / 'features.csv')
        y = pd.read_csv(self.data_dir / 'labels.csv').squeeze('columns')
        
        with open(self.data_dir / 'feature_names.txt') as f:
            self.feature_names = [line.strip() for line in f]
        
        print(f"  Features: {X.shape}")
        print(f"  Classes: {np.unique(y)}")
        
        split_idx = int(len(X) * 0.7)
        self.X_train = X.iloc[:split_idx].copy()
        self.X_test = X.iloc[split_idx:].copy()
        self.y_train = y.iloc[:split_idx].copy()
        self.y_test = y.iloc[split_idx:].copy()

        from sklearn.preprocessing import RobustScaler
        self.scaler = RobustScaler()
        self.X_train = self.scaler.fit_transform(self.X_train)
        self.X_test = self.scaler.transform(self.X_test)
        
        print(f"  Train: {self.X_train.shape[0]:,} samples")
        print(f"  Test: {self.X_test.shape[0]:,} samples")
        
        return self
    
    def train_random_forest(self):
        """Random Forest - robust ensemble."""
        print("\n" + "="*60)
        print("Training Random Forest...")
        print("="*60)
        
        model = RandomForestClassifier(
            n_estimators=200,          # More trees
            max_depth=30,              # Deep trees for complex patterns
            min_samples_split=5,
            min_samples_leaf=2,
            max_features='sqrt',
            class_weight='balanced',   # Handle imbalanced classes
            n_jobs=-1,
            random_state=42
        )
        
        model.fit(self.X_train, self.y_train)
        
        # Evaluate
        y_pred = model.predict(self.X_test)
        acc = accuracy_score(self.y_test, y_pred)
        f1 = f1_score(self.y_test, y_pred, average='weighted')
        
        print(f"  Accuracy: {acc:.4f}")
        print(f"  F1 Score: {f1:.4f}")
        
        self.models['random_forest'] = model
        self.results['random_forest'] = {
            'accuracy': acc,
            'f1_score': f1,
            'predictions': y_pred
        }
        
        if acc > self.best_score:
            self.best_score = acc
            self.best_model = 'random_forest'
        
        return self
    
    def train_xgboost(self):
        """XGBoost - gradient boosting."""
        print("\n" + "="*60)
        print("Training XGBoost...")
        print("="*60)
        
        # Encode labels for XGBoost
        le = LabelEncoder()
        y_train_enc = le.fit_transform(self.y_train)
        y_test_enc = le.transform(self.y_test)
        
        model = XGBClassifier(
            n_estimators=200,
            max_depth=10,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            objective='multi:softmax',
            num_class=len(np.unique(self.y_train)),
            eval_metric='mlogloss',
            use_label_encoder=False,
            random_state=42
        )
        
        model.fit(
            self.X_train, y_train_enc,
            eval_set=[(self.X_test, y_test_enc)],
            verbose=False
        )
        
        # Evaluate
        y_pred_enc = model.predict(self.X_test)
        y_pred = le.inverse_transform(y_pred_enc)
        
        acc = accuracy_score(self.y_test, y_pred)
        f1 = f1_score(self.y_test, y_pred, average='weighted')
        
        print(f"  Accuracy: {acc:.4f}")
        print(f"  F1 Score: {f1:.4f}")
        
        self.models['xgboost'] = (model, le)
        self.results['xgboost'] = {
            'accuracy': acc,
            'f1_score': f1,
            'predictions': y_pred
        }
        
        if acc > self.best_score:
            self.best_score = acc
            self.best_model = 'xgboost'
        
        return self
    
    def train_lightgbm(self):
        """LightGBM - fast gradient boosting."""
        print("\n" + "="*60)
        print("Training LightGBM...")
        print("="*60)
        
        model = LGBMClassifier(
            n_estimators=200,
            max_depth=15,
            learning_rate=0.1,
            num_leaves=50,
            subsample=0.8,
            colsample_bytree=0.8,
            objective='multiclass',
            class_weight='balanced',
            random_state=42,
            verbose=-1
        )
        
        model.fit(self.X_train, self.y_train)
        
        # Evaluate
        y_pred = model.predict(self.X_test)
        acc = accuracy_score(self.y_test, y_pred)
        f1 = f1_score(self.y_test, y_pred, average='weighted')
        
        print(f"  Accuracy: {acc:.4f}")
        print(f"  F1 Score: {f1:.4f}")
        
        self.models['lightgbm'] = model
        self.results['lightgbm'] = {
            'accuracy': acc,
            'f1_score': f1,
            'predictions': y_pred
        }
        
        if acc > self.best_score:
            self.best_score = acc
            self.best_model = 'lightgbm'
        
        return self
    
    def train_lstm(self):
        """LSTM - temporal sequence patterns."""
        print("\n" + "="*60)
        print("Training LSTM...")
        print("="*60)
        
        try:
            from tensorflow import keras
            from tensorflow.keras.models import Sequential
            from tensorflow.keras.layers import LSTM, Dense, Dropout
            from tensorflow.keras.utils import to_categorical
            
            timesteps = 10
            le = LabelEncoder()
            full_X = np.vstack([self.X_train, self.X_test])
            full_y = np.concatenate([self.y_train.to_numpy(), self.y_test.to_numpy()])
            split_idx = len(self.y_train)

            X_train_seq = self._create_sequences(full_X[:split_idx], timesteps)
            X_test_seq = self._create_sequences(full_X[split_idx - timesteps + 1:], timesteps)

            y_train_enc = le.fit_transform(full_y[timesteps-1:split_idx])
            y_test_enc = le.transform(full_y[split_idx:])
            
            n_classes = len(np.unique(self.y_train))
            y_train_cat = to_categorical(y_train_enc, n_classes)
            y_test_cat = to_categorical(y_test_enc, n_classes)
            
            # Build model
            model = Sequential([
                LSTM(128, return_sequences=True, input_shape=(timesteps, X_train_seq.shape[2])),
                Dropout(0.3),
                LSTM(64),
                Dropout(0.3),
                Dense(32, activation='relu'),
                Dense(n_classes, activation='softmax')
            ])
            
            model.compile(
                optimizer='adam',
                loss='categorical_crossentropy',
                metrics=['accuracy']
            )
            
            # Train
            history = model.fit(
                X_train_seq, y_train_cat,
                epochs=20,
                batch_size=64,
                validation_split=0.2,
                verbose=0
            )
            
            # Evaluate
            y_pred_proba = model.predict(X_test_seq, verbose=0)
            y_pred_enc = np.argmax(y_pred_proba, axis=1)
            y_pred = le.inverse_transform(y_pred_enc)
            
            acc = accuracy_score(y_test_enc, y_pred_enc)
            f1 = f1_score(y_test_enc, y_pred_enc, average='weighted')
            
            print(f"  Accuracy: {acc:.4f}")
            print(f"  F1 Score: {f1:.4f}")
            
            self.models['lstm'] = (model, le, timesteps)
            self.results['lstm'] = {
                'accuracy': acc,
                'f1_score': f1,
                'predictions': y_pred
            }
            
            if acc > self.best_score:
                self.best_score = acc
                self.best_model = 'lstm'
        
        except ImportError:
            print("  TensorFlow not available, skipping LSTM")
        
        return self
    
    def _create_sequences(self, data, timesteps):
        """Create sequences for LSTM."""
        sequences = []
        for i in range(timesteps - 1, len(data)):
            sequences.append(data[i - timesteps + 1:i + 1])
        return np.array(sequences)
    
    def train_stacking_ensemble(self):
        """Stacking ensemble - combines all models."""
        print("\n" + "="*60)
        print("Training Stacking Ensemble...")
        print("="*60)
        
        from sklearn.ensemble import StackingClassifier
        from sklearn.linear_model import LogisticRegression
        
        # Base models
        estimators = [
            ('rf', RandomForestClassifier(n_estimators=100, random_state=42)),
            ('xgb', XGBClassifier(n_estimators=100, use_label_encoder=False, eval_metric='mlogloss', random_state=42)),
            ('lgbm', LGBMClassifier(n_estimators=100, verbose=-1, random_state=42))
        ]
        
        # Meta-learner
        model = StackingClassifier(
            estimators=estimators,
            final_estimator=LogisticRegression(max_iter=1000),
            cv=5
        )
        
        model.fit(self.X_train, self.y_train)
        
        # Evaluate
        y_pred = model.predict(self.X_test)
        acc = accuracy_score(self.y_test, y_pred)
        f1 = f1_score(self.y_test, y_pred, average='weighted')
        
        print(f"  Accuracy: {acc:.4f}")
        print(f"  F1 Score: {f1:.4f}")
        
        self.models['stacking'] = model
        self.results['stacking'] = {
            'accuracy': acc,
            'f1_score': f1,
            'predictions': y_pred
        }
        
        if acc > self.best_score:
            self.best_score = acc
            self.best_model = 'stacking'
        
        return self
    
    def evaluate_all(self):
        """Detailed evaluation for all models."""
        print("\n" + "="*60)
        print("EVALUATION SUMMARY")
        print("="*60)
        
        # Comparison table
        print("\nModel Performance:")
        print(f"{'Model':<20} {'Accuracy':>10} {'F1-Score':>10}")
        print("-" * 42)
        
        for name, res in self.results.items():
            print(f"{name:<20} {res['accuracy']:>10.4f} {res['f1_score']:>10.4f}")
        
        print("\n" + "="*60)
        print(f"BEST MODEL: {self.best_model} (Accuracy: {self.best_score:.4f})")
        print("="*60)
        
        # Detailed report for best model
        y_pred = self.results[self.best_model]['predictions']
        
        print("\nClassification Report (Best Model):")
        print(classification_report(self.y_test, y_pred, zero_division=0))
        
        # Confusion matrix
        cm = confusion_matrix(self.y_test, y_pred)
        self._plot_confusion_matrix(cm)
        
        return self
    
    def _plot_confusion_matrix(self, cm):
        """Plot and save confusion matrix."""
        plt.figure(figsize=(12, 10))
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', cbar=True)
        plt.title(f'Confusion Matrix - {self.best_model}')
        plt.ylabel('True Label')
        plt.xlabel('Predicted Label')
        plt.tight_layout()
        plt.savefig(self.output_dir / f'{self.best_model}_confusion_matrix.png', dpi=300)
        plt.close()
        
        print(f"\n✓ Saved confusion matrix: {self.best_model}_confusion_matrix.png")
    
    def save_best_model(self):
        """Save best model and metadata."""
        print(f"\nSaving best model ({self.best_model})...")
        
        # Save model
        model = self.models[self.best_model]
        model_path = self.output_dir / f'best_model_{self.best_model}.pkl'
        joblib.dump(model, model_path)
        
        # Save scaler
        scaler_path = self.output_dir / 'scaler.pkl'
        joblib.dump(self.scaler, scaler_path)
        
        # Save feature names
        features_path = self.output_dir / 'feature_names.txt'
        with open(features_path, 'w') as f:
            for name in self.feature_names:
                f.write(f"{name}\n")
        
        # Save metadata
        metadata = {
            'model_type': self.best_model,
            'accuracy': float(self.best_score),
            'f1_score': float(self.results[self.best_model]['f1_score']),
            'n_features': len(self.feature_names),
            'classes': [int(c) for c in np.unique(self.y_train)],
            'trained_on': pd.Timestamp.now().isoformat()
        }
        
        metadata_path = self.output_dir / 'model_metadata.json'
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"\n✓ Saved:")
        print(f"  Model: {model_path}")
        print(f"  Scaler: {scaler_path}")
        print(f"  Features: {features_path}")
        print(f"  Metadata: {metadata_path}")
        
        return self
    
    def feature_importance_analysis(self):
        """Analyze feature importance."""
        if self.best_model in ['random_forest', 'xgboost', 'lightgbm']:
            print("\nFeature Importance Analysis...")
            
            if self.best_model == 'random_forest':
                importances = self.models[self.best_model].feature_importances_
            elif self.best_model == 'xgboost':
                importances = self.models[self.best_model][0].feature_importances_
            else:  # lightgbm
                importances = self.models[self.best_model].feature_importances_
            
            # Top 20 features
            indices = np.argsort(importances)[::-1][:20]
            
            plt.figure(figsize=(10, 8))
            plt.barh(range(20), importances[indices][::-1])
            plt.yticks(range(20), [self.feature_names[i] for i in indices][::-1])
            plt.xlabel('Importance')
            plt.title('Top 20 Feature Importances')
            plt.tight_layout()
            plt.savefig(self.output_dir / 'feature_importance.png', dpi=300)
            plt.close()
            
            print(f"✓ Saved feature importance plot")
            
            # Save to CSV
            importance_df = pd.DataFrame({
                'feature': [self.feature_names[i] for i in indices],
                'importance': importances[indices]
            })
            importance_df.to_csv(self.output_dir / 'feature_importance.csv', index=False)
        
        return self


def main():
    """Complete training pipeline."""
    trainer = SWATMultiClassTrainer()
    
    trainer.load_data()
    trainer.train_random_forest()
    trainer.train_xgboost()
    trainer.train_lightgbm()
    trainer.train_lstm()
    trainer.train_stacking_ensemble()
    trainer.evaluate_all()
    trainer.feature_importance_analysis()
    trainer.save_best_model()
    
    print("\n" + "="*60)
    print("TRAINING COMPLETE")
    print("="*60)


if __name__ == '__main__':
    main()
