class BlenderAddonVersionUpdater {
  updateContent(content, version) {
    const [major, minor, patch] = version.split('.');
    content = content.replace(
      /(__addon_version__\s*=\s*")\d+\.\d+\.\d+(")/,
      `$1${version}$2`,
    );
    content = content.replace(
      /("version":\s*\()\d+,\s*\d+,\s*\d+(\))/,
      `$1${major}, ${minor}, ${patch}$2`,
    );
    return content;
  }
}

module.exports = BlenderAddonVersionUpdater;
