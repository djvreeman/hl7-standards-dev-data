import sqlite3
import argparse

def get_target_ids(db_path, input_id):
    # Connect to the SQLite database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # SQL query to find the corresponding TargetKey Ids for the given SourceKey Id
    query = """
    SELECT P.Id 
    FROM Packages P 
    INNER JOIN DependencyList D ON P.PackageKey = D.TargetKey
    WHERE D.SourceKey = (SELECT PackageKey FROM Packages WHERE Id = ?)
    """
    
    # Execute the query
    cursor.execute(query, (input_id,))
    target_ids = cursor.fetchall()

    # Close the connection
    conn.close()

    return target_ids

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find target package IDs based on a source package ID.")
    parser.add_argument("-db", "--database", required=True, help="Path to the SQLite database file")
    parser.add_argument("-id", "--input_id", required=True, help="Input 'Id' from the 'Packages' table")

    args = parser.parse_args()

    # Get the target IDs
    target_ids = get_target_ids(args.database, args.input_id)

    # Print the target IDs
    print("Target IDs:")
    for id_tuple in target_ids:
        print(id_tuple[0])
