from ashare_research.mining.model import AlphaGPTLite


def test_same_seed_generates_same_formula_sequence() -> None:
    a = AlphaGPTLite(seed=0)
    b = AlphaGPTLite(seed=0)

    seq_a = [a.generate().expression.normalized() for _ in range(5)]
    seq_b = [b.generate().expression.normalized() for _ in range(5)]

    assert seq_a == seq_b
