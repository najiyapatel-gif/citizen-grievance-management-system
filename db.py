import mysql.connector

def get_connection():
    connection = mysql.connector.connect(
        host="localhost",
        user="root",
        password="najiya",
        database="grievance_db",
        port=3306
    )
    return connection

try:
    conn = get_connection()

    if conn.is_connected():
        print("MySQL connection successful!")

    conn.close()

except mysql.connector.Error as err:
    print("Connection failed:", err)