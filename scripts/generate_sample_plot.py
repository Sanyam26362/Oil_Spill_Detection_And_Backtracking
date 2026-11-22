import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

# ----------------------------------------------------------------------
# 1. Canvas Styling (Dark Scientific Mode)
# ----------------------------------------------------------------------
plt.style.use("dark_background")
fig, ax = plt.subplots(figsize=(10, 8), dpi=150)
fig.patch.set_facecolor("#0a0a0a")
ax.set_facecolor("#0a0a0a")

# ----------------------------------------------------------------------
# 2. Synthetic SAR Satellite Patch (Simulating ow-0009.jpg)
# ----------------------------------------------------------------------
# Coordinate extent: [min_lon, max_lon, min_lat, max_lat]
sar_extent = [34.83, 34.96, 34.56, 34.68]

# Generate realistic SAR speckle noise (Rayleigh / Gaussian mix)
np.random.seed(42)
sar_patch = np.random.normal(loc=130, scale=30, size=(500, 450)).clip(0, 255)

# Simulate a low-backscatter dark slick patch inside the radar image
y_grid, x_grid = np.ogrid[:500, :450]
slick_mask = (
    ((x_grid - 210) ** 2) / (35**2) + ((y_grid - 260) ** 2) / (160**2)
) <= 1
sar_patch[slick_mask] = np.random.normal(loc=45, scale=12, size=slick_mask.sum()).clip(0, 255)

# Render grayscale SAR raster onto the geographic plane
ax.imshow(
    sar_patch,
    cmap="gray",
    extent=sar_extent,
    origin="upper",
    aspect="auto",
    alpha=0.92,
)

# ----------------------------------------------------------------------
# 3. Detection Bounding Boxes & Confidence Labels
# ----------------------------------------------------------------------
# Box 1: Primary detection [lon, lat, width, height]
box1 = patches.Rectangle(
    (34.880, 34.575),
    0.022,
    0.075,
    linewidth=1.2,
    edgecolor="#707070",
    facecolor="none",
)
ax.add_patch(box1)
ax.text(
    34.881,
    34.654,
    "oil_spill 0.75",
    color="#d0d0d0",
    fontsize=7.5,
    family="monospace",
)

# Box 2: Smaller secondary detection
box2 = patches.Rectangle(
    (34.908, 34.640),
    0.015,
    0.018,
    linewidth=1.2,
    edgecolor="#707070",
    facecolor="none",
)
ax.add_patch(box2)
ax.text(
    34.909,
    34.661,
    "oil_spill 0.20",
    color="#d0d0d0",
    fontsize=7.5,
    family="monospace",
)

# ----------------------------------------------------------------------
# 4. AIS Vessel Trajectories & Intersects
# ----------------------------------------------------------------------
# Vessel 1: Intersecting Culprit Track (Cyan)
vessel_1_lons = np.linspace(34.80, 35.01, 14)
vessel_1_lats = np.linspace(34.52, 34.71, 14)
ax.plot(
    vessel_1_lons,
    vessel_1_lats,
    color="#00ffcc",
    linestyle="--",
    linewidth=1.8,
    marker="o",
    markersize=5,
    markerfacecolor="#00ffcc",
    markeredgecolor="#ffffff",
    markeredgewidth=0.6,
    label="Vessel 435569889",
)

# Vessel 2: Background Comparison Track (Magenta / Purple)
vessel_2_lons = np.array([34.80, 34.85, 34.90, 34.96])
vessel_2_lats = np.array([34.71, 34.705, 34.698, 34.692])
ax.plot(
    vessel_2_lons,
    vessel_2_lats,
    color="#bd00ff",
    linestyle="--",
    linewidth=1.4,
    marker="o",
    markersize=4,
    markerfacecolor="#bd00ff",
    label="Vessel 483802398",
)

# ----------------------------------------------------------------------
# 5. Coordinate Axes, Grid & Legend
# ----------------------------------------------------------------------
ax.set_title(
    "AIS Intersects for Satellite Pass: ow-0009.jpg\nAcquired: 2019-01-19 03:42:58",
    fontsize=11,
    color="white",
    pad=14,
)
ax.set_xlabel("Longitude", fontsize=9, color="#aaaaaa", labelpad=8)
ax.set_ylabel("Latitude", fontsize=9, color="#aaaaaa", labelpad=8)

ax.set_xlim(34.76, 35.03)
ax.set_ylim(34.48, 34.73)

ax.tick_params(colors="#aaaaaa", labelsize=8.5)
for spine in ax.spines.values():
    spine.set_color("#333333")

ax.grid(True, linestyle="--", linewidth=0.5, color="#222222", alpha=0.7)

legend = ax.legend(
    loc="upper right",
    facecolor="#141414",
    edgecolor="#333333",
    fontsize=8.5,
    labelcolor="white",
)
legend.get_frame().set_alpha(0.85)

# ----------------------------------------------------------------------
# 6. Save and Display
# ----------------------------------------------------------------------
output_filename = "sample_ais_satellite_intersect.png"
plt.tight_layout()
plt.savefig(output_filename, dpi=200, facecolor=fig.get_facecolor())
plt.show()
print(f"Generated successfully: {output_filename}")