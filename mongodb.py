from pymongo import MongoClient
import atexit
from bson import ObjectId
import logging
from datetime import datetime, timezone

# Replace with your actual connection string
uri = "mongodb+srv://esdhanush:esdhanush@chatbot-tenant.ygawpu1.mongodb.net/"
client = MongoClient(uri)

# Ensure the client is closed on shutdown
atexit.register(client.close)

# Access database and collection
db = client["Chatbot-Tenant"]
collection = db["tenants"]

# Add new collection
users = db["users"]

def insert_tenant(data):
    """Insert tenant data with string _id"""
    try:
        # Generate string ID
        str_id = str(ObjectId())
        
        # Add the string ID to the data before insertion
        data = {
            '_id': str_id,
            **data  # Spread the rest of the data
        }
        
        # Insert document with string ID
        db.tenants.insert_one(data)
        
        return str_id

    except Exception as e:
        logging.error(f"Error inserting tenant: {e}")
        return None

def get_tenant(tenant_id):
    """Get tenant data by string ID"""
    try:
        # Search directly by string ID
        tenant = db.tenants.find_one({"_id": tenant_id})
        return tenant
    except Exception as e:
        logging.error(f"Error getting tenant: {e}")
        return None

def get_tenant_by_id(tenant_id):
    """Get tenant data by string ID"""
    try:
        # Search directly by string ID
        tenant = db.tenants.find_one({"_id": tenant_id})
        if not tenant:
            # Try searching by ObjectId if string ID fails
            try:
                tenant = db.tenants.find_one({"_id": ObjectId(tenant_id)})
            except:
                pass
        return tenant
    except Exception as e:
        logging.error(f"Error getting tenant by ID: {e}")
        return None

def update_tenant_status(tenant_id, status):
    """Update tenant status using string ID"""
    try:
        result = db.tenants.update_one(
            {"_id": tenant_id},
            {"$set": {"status": status}}
        )
        return result.modified_count > 0
    except Exception as e:
        logging.error(f"Error updating tenant status: {e}")
        return False

def update_tenant_results(tenant_id, results):
    """Update tenant results using string ID"""
    try:
        result = db.tenants.update_one(
            {"_id": tenant_id},
            {"$set": {
                "processing_results": results,
                "processed_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        return result.modified_count > 0
    except Exception as e:
        logging.error(f"Error updating tenant results: {e}")
        return False

def create_user(tenant_id: str) -> str:
    """Create a new anonymous user and return the user_id"""
    try:
        now = datetime.now(timezone.utc).isoformat()
        user_data = {
            "_id": str(ObjectId()),
            "tenant_id": tenant_id,
            "created_at": now,
            "last_active": now
        }
        
        result = users.insert_one(user_data)
        if result.inserted_id:
            return user_data["_id"]
        return None
        
    except Exception as e:
        logging.error(f"Error creating user: {e}")
        return None

def update_user_last_active(user_id: str):
    """Update user's last active timestamp"""
    try:
        users.update_one(
            {"_id": user_id},
            {"$set": {"last_active": datetime.now(timezone.utc).isoformat()}}
        )
    except Exception as e:
        logging.error(f"Error updating user last active: {e}")

def get_user(user_id: str):
    """Get user by ID"""
    try:
        return users.find_one({"_id": user_id})
    except Exception as e:
        logging.error(f"Error getting user: {e}")
        return None

