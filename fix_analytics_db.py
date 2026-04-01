import analytics
try:
    analytics.init_database()
    print("Analytics database initialized successfully!")
except Exception as e:
    print(f"Error initializing analytics DB: {e}")
