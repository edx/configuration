import random
import pprint
from deepdiff import DeepDiff
from meilisearch import Client

def docs_match(old_doc, new_doc):
    ignorable_fields = []
    diff = DeepDiff(old_doc, new_doc, ignore_order=True)
    for field in ignorable_fields:
        diff.pop(field, None)
    return diff == {}

def compare_indices(old_url, old_index, new_url, new_index, api_key=None, random_check_percentage=0.1):
    old_client = Client(old_url, api_key)
    new_client = Client(new_url, api_key)

    old_idx = old_client.index(old_index)
    new_idx = new_client.index(new_index)

    # Compare stats
    old_stats = old_idx.get_stats()
    new_stats = new_idx.get_stats()

    old_count = old_stats['numberOfDocuments']
    new_count = new_stats['numberOfDocuments']

    print("{}: Document count ({} = {})".format(
        'OK' if old_count == new_count else 'FAILURE', old_count, new_count
    ))

    # Compare settings instead of mappings
    old_settings = old_idx.get_settings()
    new_settings = new_idx.get_settings()
    diff = DeepDiff(old_settings, new_settings, ignore_order=True)
    if diff != {}:
        print("FAILURE: Index settings do not match")
        pprint.pprint(diff)
    else:
        print("OK: Index settings match")

    # Random checks
    sample_size = int(old_count * random_check_percentage)
    if sample_size == 0:
        print("Skipping random checks (too few docs)")
        return

    print(f"Checking {sample_size} random documents...")
    offset = 0
    limit = min(sample_size, 1000)  # batch size
    old_docs = old_idx.get_documents(limit=limit, offset=offset)

    checked = 0
    matching = 0
    for doc in random.sample(old_docs['results'], min(sample_size, len(old_docs['results']))):
        doc_id = doc['id']
        new_doc = new_idx.get_document(doc_id)
        if new_doc and docs_match(doc, new_doc):
            matching += 1
        else:
            print(f"FAILURE: Document with id {doc_id} does not match")
        checked += 1

    print("{}: Random documents matching ({} out of {}, {:.2f}%)".format(
        'OK' if matching == checked else 'FAILURE', matching, checked, (matching / checked * 100 if checked else 0)
    ))


if __name__ == "__main__":
    # Example usage:
    # compare_indices("http://localhost:7700", "content_old",
    #                 "http://localhost:7700", "content_new",
    #                 api_key="masterKey", random_check_percentage=0.1)
    pass
