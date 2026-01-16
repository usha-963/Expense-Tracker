import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import LabelEncoder, StandardScaler, OneHotEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
import joblib
import os
from django.conf import settings
from datetime import datetime
import numpy as np

MODEL_DIR = os.path.join(settings.BASE_DIR, 'ml_models')
os.makedirs(MODEL_DIR, exist_ok=True)

MODEL_PATH = os.path.join(MODEL_DIR, 'financial_model.joblib')
PREPROCESSOR_PATH = os.path.join(MODEL_DIR, 'preprocessor.joblib')
LABEL_ENCODER_PATH = os.path.join(MODEL_DIR, 'label_encoder.joblib')

def train_model(csv_path=None, transactions=None):
    """Train or retrain the ML model"""
    try:
        if csv_path:
            df = pd.read_csv(csv_path)
        elif transactions:
            df = pd.DataFrame.from_records(transactions.values(
                'description', 'amount', 'type', 'payment_mode', 'category__name'
            ))
            df = df.rename(columns={'category__name': 'category'})
        else:
            raise ValueError("Either csv_path or transactions must be provided")
        
        # Data cleaning
        df = df.dropna(subset=['category'])
        df = df[df['category'].str.strip() != '']
        df['description'] = df['description'].str.lower().str.strip()
        
        # Feature engineering
        numeric_features = ['amount']
        text_features = 'description'
        categorical_features = ['type', 'payment_mode']
        
        preprocessor = ColumnTransformer(
            transformers=[
                ('num', StandardScaler(), numeric_features),
                ('text', TfidfVectorizer(max_features=100, stop_words='english'), text_features),
                ('cat', OneHotEncoder(handle_unknown='ignore'), categorical_features)
            ])
        
        # Encode target
        le_category = LabelEncoder()
        y = le_category.fit_transform(df['category'])
        
        # Create and train model
        model = Pipeline([
            ('preprocessor', preprocessor),
            ('classifier', RandomForestClassifier(
                n_estimators=150,
                max_depth=10,
                random_state=42,
                class_weight='balanced'
            ))
        ])
        
        X = df[['description', 'amount', 'type', 'payment_mode']]
        model.fit(X, y)
        
        # Save components
        joblib.dump(model, MODEL_PATH)
        joblib.dump(preprocessor, PREPROCESSOR_PATH)
        joblib.dump(le_category, LABEL_ENCODER_PATH)
        
        return model
    
    except Exception as e:
        print(f"Error training model: {str(e)}")
        raise

def predict_category(description, amount, trans_type, payment_mode):
    """Predict category for a new transaction"""
    try:
        if not os.path.exists(MODEL_PATH):
            return None
            
        model = joblib.load(MODEL_PATH)
        le_category = joblib.load(LABEL_ENCODER_PATH)
        
        input_data = pd.DataFrame([{
            'description': str(description).lower().strip(),
            'amount': float(amount),
            'type': trans_type,
            'payment_mode': payment_mode
        }])
        
        y_pred = model.predict(input_data)
        return le_category.inverse_transform(y_pred)[0]
    
    except Exception as e:
        print(f"Error predicting category: {str(e)}")
        return None

def generate_spending_advice(user, amount, category, current_balance, monthly_spending, monthly_budget):
    """Generate personalized spending advice"""
    advice = []
    
    # Budget advice
    if monthly_budget > 0:
        projected_spending = monthly_spending + amount
        budget_utilization = (projected_spending / monthly_budget) * 100
        
        if budget_utilization > 90:
            advice.append(f"⚠️ Budget utilization will be {budget_utilization:.1f}% after this transaction")
        elif budget_utilization > 70:
            advice.append(f"ℹ️ Budget utilization will be {budget_utilization:.1f}%")
    
    # Balance advice
    if current_balance - amount < 1000:
        advice.append(f"⚠️ Low balance warning: ₹{current_balance - amount:,.2f} remaining")
    
    # Category advice
    category_advice = {
        'Shopping': "🛍️ Consider if this purchase is necessary",
        'Entertainment': "🎬 Look for free alternatives",
        'Dining': "🍽️ Cooking at home saves money",
    }
    
    if category and category in category_advice:
        advice.append(category_advice[category])
    
    # Amount advice
    if amount > 20000:
        advice.append("⚠️ Large transaction - consider waiting 24 hours")
    elif amount > 10000:
        advice.append("ℹ️ Significant amount - review your budget")
    
    return advice if advice else ["✅ Transaction seems reasonable"]

def retrain_model_periodically():
    """Periodically retrain the model with new data"""
    try:
        last_trained = getattr(settings, 'MODEL_LAST_TRAINED', None)
        if last_trained and (datetime.now() - last_trained).days < 7:
            return
            
        from .models import Transaction
        transactions = Transaction.objects.filter(category__isnull=False)
        
        if transactions.count() > 50:
            train_model(transactions=transactions)
            settings.MODEL_LAST_TRAINED = datetime.now()
    
    except Exception as e:
        print(f"Error in periodic retraining: {str(e)}")