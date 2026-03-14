import pytest
from backend.app.core.quality.replication import evaluate_outputs, similarity
from backend.app.core.quality.agent_quality_store import AgentQualityStore


@pytest.mark.asyncio
async def test_similarity_basic():
    a = "foo bar baz"
    b = "foo bar qux"
    sim = similarity(a, b)
    assert 0.5 < sim < 1.0


def test_evaluate_outputs_empty():
    stats = evaluate_outputs([])
    assert stats["mean_similarity"] == 1.0
    assert stats["min_similarity"] == 1.0
    assert stats["pair_count"] == 0


def test_evaluate_outputs_multiple():
    outs = ["a", "a", "a"]
    stats = evaluate_outputs(outs)
    assert stats["mean_similarity"] == 1.0
    assert stats["min_similarity"] == 1.0
    assert stats["pair_count"] == 3


@pytest.mark.asyncio
async def test_agent_quality_store_replication(tmp_path):
    dbfile = tmp_path / "rep.db"
    store = AgentQualityStore(db_path=str(dbfile))
    await store.initialize()
    outputs = ["x", "x", "x"]
    rid = await store.log_replication_run("financial_analyst", "dcf", outputs)
    assert isinstance(rid, int)
    recent = await store.get_recent_replication("financial_analyst", "dcf")
    assert len(recent) == 1
    assert recent[0]["avg_similarity"] == 1.0


@pytest.mark.asyncio
async def test_baseagent_evaluate_replication(mock_financial_analyst):
    # The mock agent returns a constant response, so replication should be perfect
    stats = await mock_financial_analyst.evaluate_replication(
        task="foo", context={"bar": 1}, runs=4
    )
    assert stats["mean_similarity"] == 1.0
    assert stats["min_similarity"] == 1.0
