# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `--tile_format zarr`: one Zarr v3 tile store per slide (`<output_dir>/<slide>.zarr`, palyim-io tile store) instead
  of the PNG tree, with resume, missing-plane reruns and a non-zero exit status on failures. Options
  `--zarr-writers` and `--zarr-tiles-per-shard`.
- Per-phase timings in the log at the end of every run, and `--timings-json`.
- Tests (pytest, run inside the image) on a synthetic OME-TIFF: Zarr vs PNG pixels, resume, read failures.

### Changed
- Update Zenodo URL in the README.
- Docker images on `python:3.12-slim-bookworm` with numpy 1.26.4, pinned through `constraints.txt`, plus
  palyim-io[zarr] from a local wheel. PNG output is unchanged.

### Fixed
- Build error due to base image changing. [#81](https://github.com/paleopollen/palyim-issues/issues/81)
- Issue related to low tile cropping throughput. [#87](https://github.com/paleopollen/palyim-issues/issues/87)

## [1.2.0] - 2025-04-22

### Added
- CITATION.cff file. [#72](https://github.com/paleopollen/palyim-issues/issues/72)

## [1.1.1] - 2025-02-04

### Fixed
- Filename splitting code to handle multiple dots in the filename. 

## [1.1.0] - 2025-01-22

### Changed

- README to include Zenodo status badge. [#50](https://github.com/paleopollen/palyim-issues/issues/50)
- Filename splitting code to handle multiple dots in the filename. [#67](https://github.com/paleopollen/palyim-issues/issues/67)

## [1.0.0] - 2024-12-16

### Added

- Basic features of NDPI Tile Cropper CLI. [#28](https://github.com/paleopollen/palyim-issues/issues/28), [#32](https://github.com/paleopollen/palyim-issues/issues/32), [#42](https://github.com/paleopollen/palyim-issues/issues/42), [#44](https://github.com/paleopollen/palyim-issues/issues/44), [#49](https://github.com/paleopollen/palyim-issues/issues/49), [#53](https://github.com/paleopollen/palyim-issues/issues/53), [#55](https://github.com/paleopollen/palyim-issues/issues/55), [#57](https://github.com/paleopollen/palyim-issues/issues/57), [#56](https://github.com/paleopollen/palyim-issues/issues/56) 
- This CHANGELOG.md file. [#62](https://github.com/paleopollen/palyim-issues/issues/62)

### Changed

- Code cleanup and other improvements. [#62](https://github.com/paleopollen/palyim-issues/issues/62)

[unreleased]: https://github.com/paleopollen/ndpi-tile-cropper-cli/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/paleopollen/ndpi-tile-cropper-cli/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/paleopollen/ndpi-tile-cropper-cli/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/paleopollen/ndpi-tile-cropper-cli/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/paleopollen/ndpi-tile-cropper-cli/releases/tag/v1.0.0
