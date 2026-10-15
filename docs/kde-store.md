# KDE Store submission

The GitHub release is ready to share independently. Publishing it on GitHub does
**not** automatically create or submit a KDE Store listing.

## User-only submission steps

1. Log in to your own KDE Store / openDesktop account and open
   <https://store.kde.org/product/add>. Without a login, this redirects to the
   openDesktop sign-in page. No account or listing has been created for you.
2. Choose **KWin Effects Plasma 6**. Start in
   [KWin Effects](https://store.kde.org/browse?cat=209&ord=latest) and select the
   Plasma 6 subcategory as appropriate. That is the exact category used by the
   tested Plasma 6 Desktop Effects discovery feed, not a full desktop theme or
   Plasma widget category.
3. Paste/adapt the listing copy below. Set the author to **ThePowershellNinja**,
   version to **0.1.0**, and license to **MIT**. Link the GitHub repository and
   release as the source/homepage and download reference.
4. Download the installable
   [neon-circuit-digital-transit-0.1.0.tar.gz](https://github.com/ThePowershellNinja/neon-circuit-digital-transit/releases/download/v0.1.0/neon-circuit-digital-transit-0.1.0.tar.gz)
   release asset and upload it as the downloadable KWin effect package.
   **Do not upload GitHub's "Source code (zip/tar.gz)" archive.**
   The installable archive has `metadata.json`, `contents/`, and `LICENSE` at its
   root; it is already suitable for `KWin/Effect` KPackage installation.
5. Upload [preview.gif](preview.gif) and/or [preview.png](preview.png), preserving
   the label that they are illustrative shader renders with synthetic content.
   These are not screenshots of a configured desktop. No private application
   data, third-party wallpaper, or theme is present.
6. Review the category, version, license, download, description, and media before
   submitting. Follow the Store's current review/upload requirements. If/when
   the listing is available in the feed, check it in **Desktop Effects > Get New
   Desktop Effects**. Listing/review/discovery timing is controlled by the Store,
   not this repository.

KDE Store generates its own discovery metadata. There is no need to distribute a
personal KNewStuff provider file. The tested system's `kwineffect.knsrc` uses
`Categories=KWin Effects Plasma 6`, `Uncompress=kpackage`, and
`KPackageStructure=KWin/Effect`. A Store listing is not inclusion in KDE core or
a distro package.

## Ready-to-adapt listing copy

**Title:** Neon Circuit Digital Transit

**Summary:** A directional digital-fragment minimize and restore effect for
KWin / Plasma 6.

**Description:**

Windows peel into hundreds of irregular, scanlined fragments. A coherent wave
starts at the icon-facing edge, while independent asymmetric curves carry the
captured window content into its native task icon. Restore retraces the same
seeded paths, joining directly into a seamless window. Unreached portions stay
intact and undistorted.

This standalone effect changes minimize/restore only. It does not include a
desktop theme, wallpaper, custom task manager, or open/close/maximize animation.
Native icon geometry is supported at any panel edge and on another output.
KWin chooses among the icon geometries published by panels/docks; a dock that
does not publish a usable native target cannot provide an icon-directed flight.

The base duration is 300 ms and honors KDE's global animation speed. The shader
uses 504 fragments for a 700 x 440 window, capped at 720 for large windows.
Performance depends on window size, resolution, driver, and concurrent effects;
large-window animation can exceed a refresh interval.

Known tested runtime: Nobara, Plasma/KWin 6.7.5, Wayland, AMD RX 7800 XT with
Mesa. Other Plasma versions, X11, GPUs/drivers, mixed-DPI setups, and HDR output
have not been verified in live KWin sessions. Requires OpenGL compositing.

Install the downloadable effect archive with:

```sh
kpackagetool6 --type KWin/Effect --install neon-circuit-digital-transit-0.1.0.tar.gz
```

Enable **Neon Circuit Digital Transit** in System Settings > Window Management >
Desktop Effects and disable other minimize effects such as Magic Lamp/Squash.
The repository README covers upgrades, removal, configuration, and limitations.

Preview: illustrative rendering of the actual shader using an original
synthetic window and neutral background, slowed for clarity. No user's desktop
or application contents are shown.

Author: ThePowershellNinja. License: MIT.

Source: <https://github.com/ThePowershellNinja/neon-circuit-digital-transit>

Release: <https://github.com/ThePowershellNinja/neon-circuit-digital-transit/releases/tag/v0.1.0>
