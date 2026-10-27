"""The deterministic tax tools, by name. The one list shared by the in-process registry
(src/orchestration/access.py), the MCP server (src/tax_math_mcp.py) and the MCP client
(src/mcp_client.py), so they can never drift apart. Imports nothing but tax_math."""
import tax_math

TAX_TOOLS = {
    fn.__name__: fn
    for fn in (
        tax_math.calculate_standard_deduction, tax_math.calculate_senior_deduction,
        tax_math.calculate_taxable_social_security, tax_math.calculate_income_tax,
        tax_math.sum_amounts, tax_math.subtract_amounts,
    )
}
