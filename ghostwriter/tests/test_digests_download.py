def test_download_rejects_path_traversal(client):
    response = client.get("/api/digests/bad..epub")
    assert response.status_code == 400


def test_download_rejects_non_epub(client):
    response = client.get("/api/digests/not-an-epub.txt")
    assert response.status_code == 400
