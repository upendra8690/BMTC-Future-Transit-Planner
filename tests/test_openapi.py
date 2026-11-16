"""The published API description must match the status codes the endpoints really return."""


def test_the_upload_endpoint_documents_the_status_codes_it_returns(client):
    responses = client.app.openapi()["paths"]["/api/admin/imports"]["post"]["responses"]
    assert "201" in responses, "a completed import returns 201"
    assert "422" in responses, "a rejected import returns 422"
    assert "200" not in responses, "the upload never returns 200"
