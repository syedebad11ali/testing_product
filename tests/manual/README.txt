KARACHI PROPERTY TRUST - TEST PACK (all fictional, testing only)

FOLDERS
documents_png/  (now public/assets/samples/) 29 sample documents (clean renders). Names: <type>_matching / <type>_mismatch,
                altered_*, ocr_challenge.jpg
documents_pdf/  (now public/assets/samples/) 28 PDF versions (real text layer -> read directly, no OCR)
photo_style/    3 "photo of paper" images: tilt, shadow, noise, JPEG compression
quality_checks/ 6 bad images for the image-quality / unreadable-document paths

HOW TO USE
1. Serve the site:  npm start   then open http://localhost:5000
2. Verify Your Document -> pick the matching document type -> Upload (or Camera: hold a
   screen showing one of these images up to the camera).
3. Compare what you see with the table below.

EXPECTED RESULTS (from headless tests; NOT yet confirmed in a browser)
- *_matching PDFs ............ DOCUMENT VERIFIED (except power_of_attorney_* see below)
- *_mismatch PDFs ............ DOCUMENT NOT VERIFIED + popup, reason shows changed field
- altered_missing_plot ....... UNABLE TO VERIFY (plot blank)
- altered_conflicting_info ... POTENTIALLY FORGED / SUSPICIOUS (header 34-C vs body 52-A)
- PNG versions of matching docs: often UNABLE TO VERIFY (OCR misreads e.g. 34-C as 34-EUR,
  CNIC 0 as 9). That is the intended safe behaviour, not a bug.
- photo_style/*.jpg: sale_deed photo and property "shadow_noise" may read partly; the
  "hard" one is expected to fail OCR -> UNABLE TO VERIFY / could not read.
- quality_checks/01_blank_white, 02_too_dark: rejected BEFORE OCR ("not clear").
- quality_checks/03_very_dark_document, 04_washed_out, 05_tiny, 06_heavy_blur: they PASS
  the app's simple brightness/contrast gate, so they go to OCR and should end at
  "could not read / UNABLE TO VERIFY". They must never be called forged.

KNOWN GAPS
- power_of_attorney_mismatch (attorney name changed) is wrongly VERIFIED: the database has
  no attorney record to compare.
- altered_multiple_mismatch matches Property B in free search (it swaps in B's details).
- The image-quality gate does not detect blur or overexposure by itself.
