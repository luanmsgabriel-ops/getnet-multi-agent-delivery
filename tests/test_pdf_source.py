import unittest
from unittest.mock import patch,Mock
from io import BytesIO
from pypdf import PdfWriter
from app.rag.pdf_source import extract_pages,capture,capture_bounded,PDF_SOURCES,MAX_PDF_BYTES

class PDFSourceTest(unittest.TestCase):
 def test_invalid_bytes(self):
  for raw in (b'',b'<html/>',b'%PDF-'+b'x'*MAX_PDF_BYTES):
   with self.assertRaises(ValueError):extract_pages(raw)
 def test_unknown_url_no_network(self):
  with patch('app.rag.pdf_source.resolve_public') as resolve:
   for fn in (capture,capture_bounded):
    with self.assertRaises(ValueError):fn('https://127.0.0.1/private.pdf')
   resolve.assert_not_called()
 def test_empty_pdf_abstains(self):
  writer=PdfWriter();writer.add_blank_page(width=100,height=100);stream=BytesIO();writer.write(stream)
  with self.assertRaises(ValueError):extract_pages(stream.getvalue())
 def test_encrypted_refused(self):
  writer=PdfWriter();writer.add_blank_page(width=100,height=100);writer.encrypt('test-only');stream=BytesIO();writer.write(stream)
  with self.assertRaises(ValueError):extract_pages(stream.getvalue())
 def test_page_limit(self):
  writer=PdfWriter()
  for _ in range(31):writer.add_blank_page(width=100,height=100)
  stream=BytesIO();writer.write(stream)
  with self.assertRaises(ValueError):extract_pages(stream.getvalue())
 def test_redirect_refused(self):
  conn=Mock();conn.getresponse.return_value.status=302
  with patch('app.rag.pdf_source.resolve_public',return_value='8.8.8.8'),patch('app.rag.pdf_source.PinnedHTTPS',return_value=conn):
   with self.assertRaises(ValueError):capture(PDF_SOURCES[0])
  conn.close.assert_called_once()

 def test_reviewed_technical_page_only(self):
  from pathlib import Path
  from app.rag.core import load_snapshot,Index
  from app.rag.fetch import SOURCES
  files=list(Path('corpus_publico').glob('9710dd88*.json'))
  self.assertEqual(len(files),1)
  snapshot=load_snapshot(files[0],SOURCES)
  self.assertEqual(len(snapshot['chunks']),1)
  self.assertIn('pagina 3',snapshot['chunks'][0])
  self.assertNotIn('0000',snapshot['chunks'][0])
  self.assertNotIn('R$',snapshot['chunks'][0])
  result=Index([snapshot]).search('Get Smart Bluetooth touchscreen')
  self.assertTrue(result['candidates'])
