Region: x0=71680 y0=43008 size=16384 px, Z=9; raw 7.25 GB; setId 0.7 s; Bio-Formats read 2048² chunk: n=576 mean 0.171 s median 0.115 s, pass total 313 s
Bio-Formats read on the cropper's 1792-stride grid: n=729 mean 0.130 s, pass total 95 s (= read cost of today's PNG output for this region: 81 tiles)

| Format | files | GB on disk | encode wall 1w (s) | end-to-end est. 1w (s) | peak RSS MB (parent/child) | 4 workers (s) | 8 workers (s) | tile stack (s) | 256² window ×Z (ms) | full plane (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| A PNG tree | 730 | 1.11 | 354 | 449 | 1001/0 | 123 | 83 | 0.461 | 481.6 | 4.8 |
| A-zip PNG + zip | 1 | 1.11 | 397 | 492 | 930/0 | n/a | n/a | – | – | – |
| B Zarr v3 chunked | 65 | 1.35 | 106 | 204 | 1322/0 | 54 | 43 | 0.111 | 92.7 | 2.5 |
| C Zarr v3 sharded 4×4 zstd | 5 | 1.35 | 77 | 175 | 1579/0 | 24 | n/a | 0.069 | 27.7 | 0.9 |
| C-lz4 Zarr v3 sharded 4×4 lz4 | 5 | 2.82 | 78 | 177 | 1924/0 | n/a | n/a | 0.061 | 21.5 | 1.1 |
| C-z Zarr v3 sharded per plane 8×8 | 10 | 1.35 | 44 | 143 | 1515/0 | 27 | 59 | 0.067 | 28.1 | 0.7 |
| D HDF5 blosc-zstd | 1 | 1.35 | 73 | 172 | 1118/1 | n/a | n/a | 0.285 | 108.9 | 0.9 |

end-to-end est. = Bio-Formats read pass (99 s aligned chunks; 95 s on the 1792 grid for PNG) + encode wall (native arm64).
