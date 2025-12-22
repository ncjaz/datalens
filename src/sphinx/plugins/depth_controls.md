# Depth Visualization Controls

The Capture plugin provides comprehensive depth visualization controls for RealSense cameras, allowing you to preview and adjust depth data in real-time.

## Overview

Depth visualization converts raw depth data (uint16 millimeters) into grayscale RGB images for preview. The visualization system supports both automatic and manual range scaling to optimize contrast and detail visibility.

## Key Features

- **Auto-scaling with percentile filtering** for robust visualization
- **Manual near/far range control** for fixed-range applications
- **Real-time depth alignment** to RGB camera viewpoint
- **Stream mode switching** between RGB and depth preview
- **Flexible save options** for RGB and/or depth data

## Depth Sensor Configuration

### Enable Depth Sensor

**Location**: Device group → Depth Sensor toggle

Controls whether the depth stream is enabled on the RealSense camera.

- **Options**: Disabled / Enabled
- **Default**: Disabled
- **Behavior**:
  - **Disabled**: Only RGB stream is captured
  - **Enabled**: Both RGB and depth streams are captured
  - Requires camera to be stopped before toggling (prevents mid-stream reconfiguration)

### Depth Alignment

**Location**: Device group → Depth Alignment toggle

Controls whether depth frames are aligned to the RGB camera's viewpoint.

- **Options**: Standard / Aligned to RGB
- **Default**: Standard
- **Behavior**:
  - **Standard**: Depth data in native depth camera coordinate system
  - **Aligned to RGB**: Depth data reprojected to RGB camera viewpoint using RealSense SDK alignment filter (`rs.align(rs.stream.color)`)
  - Only applies when depth sensor is enabled
  - Aligned mode ensures depth and RGB pixels correspond spatially

**Use Cases**:
- **Standard**: Fastest performance, native depth accuracy
- **Aligned to RGB**: Required for pixel-wise RGB-D operations, AR overlays, or combining color and depth data

## Visualization Settings

### Stream Mode

**Location**: Capture group → Stream toggle (RGB / Depth)

Switches the preview display between RGB and depth visualization.

- **Options**: RGB / Depth
- **Default**: RGB
- **Behavior**:
  - **RGB**: Shows color camera feed
  - **Depth**: Shows grayscale depth visualization with applied range settings
  - Depth mode only available when depth sensor is enabled
  - Settings panel title updates to match selected stream

### Auto-Scale Depth Range

**Location**: Depth Settings → Auto-scale depth range (checkbox)

Automatically adjusts the depth range for optimal visualization contrast.

- **Default**: Enabled
- **When Enabled**:
  - Calculates range from current frame data
  - Uses either percentile or min/max values (see below)
  - Adapts to scene depth distribution
- **When Disabled**:
  - Uses fixed near/far distances (manual mode)
  - Consistent range across all frames

**Algorithm** (when enabled):
```python
# Get valid depth values (exclude zeros)
valid_depths = depth_frame[depth_frame > 0]

if use_percentiles:
    # Percentile mode: filter outliers
    depth_min = np.percentile(valid_depths, low_percentile)   # default: 1%
    depth_max = np.percentile(valid_depths, high_percentile)  # default: 99%
else:
    # Min/max mode: use absolute range
    depth_min = valid_depths.min()
    depth_max = valid_depths.max()

# Normalize and convert to grayscale
normalized = (depth_frame - depth_min) / (depth_max - depth_min)
grayscale = np.clip(normalized, 0.0, 1.0) * 255.0
```

### Use Percentiles for Auto-Scale

**Location**: Depth Settings → Use percentiles for auto-scale (checkbox)

Controls the auto-scaling calculation method.

- **Default**: Enabled
- **When Enabled** (percentile mode):
  - Uses configurable percentile thresholds (default 1% to 99%)
  - Filters out extreme outliers for better contrast
  - More robust to noisy depth readings
  - **Example**: At 1%/99%, the closest 1% and farthest 1% of pixels are clamped
- **When Disabled** (min/max mode):
  - Uses absolute minimum and maximum depth values
  - Full range representation
  - May reduce contrast if outliers are present

**Recommended Settings**:
- **Percentile mode (default)**: Most scenes, indoor environments, objects at varying distances
- **Min/max mode**: Scenes with uniform depth distribution, precision depth mapping

### Percentile Thresholds

**Location**: Depth Settings → Percentiles (dual spinbox)

Defines the percentile range when percentile mode is enabled.

- **Low Percentile**:
  - Range: 0.0% to 100.0%
  - Default: 1.0%
  - Step: 0.5%
  - **Effect**: Depth values below this percentile appear black
  - **Higher values** → Increase contrast by ignoring closer objects

- **High Percentile**:
  - Range: 0.0% to 100.0%
  - Default: 99.0%
  - Step: 0.5%
  - **Effect**: Depth values above this percentile appear white
  - **Lower values** → Increase contrast by ignoring farther objects

**Example Adjustments**:
- **High contrast** (tight range): 5% / 95%
- **Balanced** (default): 1% / 99%
- **Full range**: 0% / 100% (equivalent to min/max mode)

### Manual Range Control

**Location**: Depth Settings → Near / Far spinboxes

Defines the fixed depth range when auto-scale is disabled.

- **Near Distance**:
  - Range: 0.0 m to 20.0 m
  - Default: 0.2 m
  - Step: 0.05 m
  - **Effect**: Objects at or closer than this distance appear black

- **Far Distance**:
  - Range: 0.0 m to 20.0 m
  - Default: 2.0 m
  - Step: 0.05 m
  - **Effect**: Objects at or farther than this distance appear white

**Use Cases**:
- **Fixed-range applications**: Consistent visualization across multiple captures
- **Known scene depth**: When you know the approximate depth range (e.g., desktop objects at 0.5m to 1.5m)
- **Calibration**: Comparing depth accuracy at specific distances

## Save Options

**Location**: Save group → Formats toggle (RGB / Depth)

Controls which data streams are saved during capture.

- **RGB**: Save color images (always available)
- **Depth**: Save depth data (only available when depth sensor is enabled)
- **Both**: Save synchronized RGB and depth pairs
- **Format**: Non-exclusive toggle (can select both)

**Important Notes**:
- Depth visualization settings (percentiles, near/far) affect **preview only**
- Saved depth data is always raw uint16 millimeters, not grayscale
- Alignment setting **does** affect saved depth data (Standard vs Aligned to RGB)

## Comparison: DatalensV1 vs V2

| Feature | V1 | V2 (Current) | Status |
|---------|----|--------------| ------ |
| Depth sensor enable/disable | Checkbox | Toggle (Disabled/Enabled) | ✅ Improved UI |
| Depth alignment | ❌ Not available | Toggle (Standard/Aligned to RGB) | ✅ **NEW** |
| Auto-scale range | Checkbox | Checkbox | ✅ Same |
| Percentile mode | Checkbox | Checkbox | ✅ Same |
| Percentile range | Dual spinbox (1% - 99%) | Dual spinbox (1% - 99%) | ✅ Same |
| Manual near/far | Dual spinbox (0.2m - 2.0m) | Dual spinbox (0.2m - 2.0m) | ✅ Same |
| Stream mode (RGB/Depth) | Toggle | Toggle | ✅ Same |
| Depth visualization | Grayscale | Grayscale | ✅ Same |
| Tooltips | ❌ None | ✅ Comprehensive tooltips | ✅ **NEW** |
| Accessibility | ❌ Checkbox hidden until enabled | ✅ Always visible when RealSense selected | ✅ Improved |

### Key Improvements in V2

1. **Depth Alignment**: New feature using RealSense SDK's `rs.align()` for pixel-perfect RGB-D correspondence
2. **UI Consistency**: Replaced checkbox with toggle widget matching the rest of the capture UI
3. **Better Accessibility**: Depth controls are always visible when RealSense camera is selected (no chicken-and-egg problem)
4. **Comprehensive Tooltips**: All controls have detailed tooltips explaining behavior and defaults
5. **Improved Documentation**: Complete depth control reference with algorithms and use cases

## Technical Details

### Depth Data Format

- **Raw Depth**: Uint16 values in millimeters
- **Preview Depth**: Uint8 grayscale (0-255) after range normalization
- **Saved Depth**: Always raw uint16 millimeters (visualization settings don't affect saved data)

### Normalization Algorithm

```python
def render_depth_to_rgb(depth_u16):
    """
    Convert depth frame (uint16 mm) to RGB888 grayscale preview.

    1. Filter invalid values (depth == 0)
    2. Calculate range (percentile or min/max)
    3. Normalize to [0.0, 1.0]
    4. Convert to uint8 [0, 255]
    5. Replicate to 3 channels for RGB display
    """
    valid = depth_u16 > 0

    if auto_scale:
        vals = depth_u16[valid]
        if use_percentiles:
            depth_min = np.percentile(vals, low_percentile)
            depth_max = np.percentile(vals, high_percentile)
        else:
            depth_min = vals.min()
            depth_max = vals.max()
    else:
        depth_min = near_distance_m * 1000.0  # Convert to mm
        depth_max = far_distance_m * 1000.0

    # Normalize
    normalized = (depth_u16.astype(float) - depth_min) / (depth_max - depth_min)
    normalized = np.clip(normalized, 0.0, 1.0)

    # Convert to grayscale uint8
    grayscale = (normalized * 255.0).astype(np.uint8)
    grayscale[~valid] = 0  # Invalid pixels = black

    # Replicate to RGB
    return np.repeat(grayscale[:, :, None], 3, axis=2)
```

### RealSense Alignment Process

When "Aligned to RGB" is selected:

```python
# In capture loop (service.py)
if align_depth_to_color:
    align = rs.align(rs.stream.color)  # Create alignment object
    frames = pipeline.wait_for_frames()
    frames = align.process(frames)  # Apply alignment

    # Now depth and color frames have matching resolution and viewpoint
    color_frame = frames.get_color_frame()
    depth_frame = frames.get_depth_frame()
```

**Effect**:
- Depth resolution matches RGB resolution (e.g., 1920x1080)
- Depth pixels correspond exactly to RGB pixels (pixel [x, y] in depth matches pixel [x, y] in RGB)
- Enables pixel-wise RGB-D operations without manual transformation

**Performance**:
- Slight CPU overhead for alignment filter
- Recommended for most RGB-D applications

## Best Practices

### General Recommendations

1. **Start with defaults**: Auto-scale enabled, percentiles 1%/99%
2. **Adjust percentiles** if scene has extreme outliers (e.g., very close or far objects)
3. **Use manual mode** for consistent visualization across multiple captures
4. **Enable alignment** when combining RGB and depth data for pixel-wise operations

### Common Use Cases

**Indoor Object Scanning** (0.5m - 2.0m):
- Auto-scale: Enabled
- Percentiles: 1% / 99% (default)
- Alignment: Aligned to RGB (for texture mapping)

**Desktop Workspace** (0.3m - 1.5m):
- Auto-scale: Disabled
- Near: 0.3 m
- Far: 1.5 m
- Alignment: Standard (faster preview)

**Room Mapping** (1.0m - 5.0m):
- Auto-scale: Enabled
- Percentiles: 2% / 98% (filter close/far outliers)
- Alignment: Standard (native depth accuracy)

**High-Contrast Scenes** (mixed near/far):
- Auto-scale: Enabled
- Percentiles: 5% / 95% (aggressive outlier filtering)
- Alignment: As needed

## Troubleshooting

### Depth Preview Shows Mostly Black/White

**Cause**: Range too wide or too narrow for scene

**Solutions**:
1. Enable auto-scale (should adapt automatically)
2. If auto-scale is on, adjust percentile thresholds
3. Switch to manual mode and adjust near/far to match scene depth

### Depth Values Look Noisy

**Cause**: RealSense depth sensor limitations or lighting conditions

**Solutions**:
1. Use percentile mode (filters outliers automatically)
2. Increase low percentile (e.g., 2% or 5%) to filter noise
3. Ensure adequate lighting and avoid IR interference
4. Check RealSense settings (exposure, gain, etc.)

### Depth and RGB Don't Align

**Cause**: Using "Standard" depth mode

**Solution**:
- Switch to "Aligned to RGB" depth alignment mode
- Alignment is required for pixel-wise RGB-D correspondence

### Controls Disabled/Greyed Out

**Cause**: Camera is running (stream reconfiguration not allowed)

**Solution**:
- Stop the camera before changing depth sensor or alignment settings
- Preview settings (auto-scale, percentiles, near/far) can be adjusted while streaming

## See Also

- [Capture Plugin Overview](capture.md)
- [RealSense Integration](capture.md#realsense-integration)
- [Plugin Settings](settings.md)
- [Data Export](writer.md)
