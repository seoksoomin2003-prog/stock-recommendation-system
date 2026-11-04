import unittest

from providers.sec_parser import parse_ownership_xml
from providers.adapters import SECProviderAdapter


class TestSecParser(unittest.TestCase):
    def test_form4_transaction_is_normalized(self):
        xml = """<ownershipDocument><documentType>4</documentType><periodOfReport>2026-01-02</periodOfReport>
        <reportingOwner><reportingOwnerId><rptOwnerCik>1</rptOwnerCik><rptOwnerName>A</rptOwnerName></reportingOwnerId>
        <reportingOwnerRelationship><officerTitle>CEO</officerTitle></reportingOwnerRelationship></reportingOwner>
        <nonDerivativeTable><nonDerivativeTransaction><transactionDate><value>2026-01-01</value></transactionDate>
        <transactionCoding><transactionCode>P</transactionCode></transactionCoding><transactionAmounts>
        <transactionShares><value>10</value></transactionShares><transactionPricePerShare><value>20</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
        <postTransactionAmounts><sharesOwnedFollowingTransaction><value>30</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
        </nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>"""
        values = parse_ownership_xml(xml, "s", "1", "https://sec.example/form4.xml")
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0]["transaction_value"], 200.0)

    def test_non_ownership_document_is_not_synthetic(self):
        self.assertEqual(parse_ownership_xml("<x></x>", "s", "1", "x"), [])

    def test_xsl_url_is_converted_to_raw_archive_xml(self):
        rendered = "https://www.sec.gov/Archives/edgar/data/1/2/xslF345X06/form4.xml"
        self.assertEqual(SECProviderAdapter._raw_ownership_url(rendered),
                         "https://www.sec.gov/Archives/edgar/data/1/2/form4.xml")
