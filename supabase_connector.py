import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
try:
    supabase: Client = create_client(url, key)
    print("Connection successful")
except:
    print("Connection failed")


def insert_row(t_name: str, row: dict):
    response = (
        supabase.table(t_name)
        .insert(row)
        .execute()
    )
    return response

def example_insert(t_name):
    response = (
        supabase.table(t_name)
        .insert({
            "user_name": "pelago",
            "password": "serafin",
            "web_address": "mallowcheeses.ie",
            "phone_number": "0892571",
            "account_holder": "Sharon Mitchell",
            "eircode": "E78GH95"
        })
        .execute()
    )
    return response

if __name__ == '__main__':
    example_insert("producer")