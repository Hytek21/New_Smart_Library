import os
import time
import requests
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "library_system.settings")
django.setup()

from library.models import Book

def get_publication_year(title, author=None, isbn=None):
    """
    Tries to find the publication year using Open Library API.
    Returns the year as an integer or None.
    """
    try:
        # 1. Try by ISBN first (most accurate)
        if isbn and len(isbn) in [10, 13]:
            url = f"https://openlibrary.org/isbn/{isbn}.json"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "publish_date" in data:
                    year = extract_year(data["publish_date"])
                    if year:
                        return year

        # 2. Search by title + author
        query = title
        if author:
            query += f" {author}"

        url = "https://openlibrary.org/search.json"
        params = {
            "q": query,
            "limit": 3
        }
        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            docs = data.get("docs", [])
            for doc in docs:
                # Prefer exact-ish title match
                if "first_publish_year" in doc:
                    return doc["first_publish_year"]
                if "publish_year" in doc and doc["publish_year"]:
                    return doc["publish_year"][0]

    except Exception as e:
        print(f"  Error looking up '{title}': {e}")

    return None

def extract_year(date_str):
    """Extract a 4-digit year from a date string."""
    if not date_str:
        return None
    import re
    match = re.search(r"(19|20)\d{2}", str(date_str))
    if match:
        return int(match.group())
    return None

def update_books():
    books = Book.objects.filter(publication_year__isnull=True)
    total = books.count()
    print(f"Found {total} books without publication year.\n")

    updated = 0
    failed = 0

    for i, book in enumerate(books, 1):
        print(f"[{i}/{total}] Looking up: {book.title[:60]}...")

        year = get_publication_year(
            title=book.title,
            author=book.author,
            isbn=book.isbn
        )

        if year:
            book.publication_year = year
            book.save(update_fields=["publication_year"])
            print(f"  → Found year: {year}")
            updated += 1
        else:
            print(f"  → Not found")
            failed += 1

        # Be polite to the API
        time.sleep(1)

    print("\n" + "=" * 40)
    print(f"Updated: {updated}")
    print(f"Not found: {failed}")
    print("=" * 40)

if __name__ == "__main__":
    update_books()