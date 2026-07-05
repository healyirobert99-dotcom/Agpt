from ashare_research.factors.vocabulary import MAX_FORMULA_LENGTH
from ashare_research.mining.generator import FormulaGenerator
from ashare_research.mining.model import AlphaGPTLite


def test_generated_formulas_parse_with_phase1_expression() -> None:
    generator = FormulaGenerator(AlphaGPTLite(seed=0))

    formulas = generator.generate_batch(10)

    for generated in formulas:
        valid, reason = generated.expression.validate()
        assert valid, reason
        assert len(generated.expression.tokens) <= MAX_FORMULA_LENGTH
        assert generated.expression.to_string()
