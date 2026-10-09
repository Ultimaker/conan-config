# Ultimaker Conan configuration files

**Conan 2 configuration for UltiMaker and Community developers**

### Installation
```bash
conan config install https://github.com/Ultimaker/conan-config.git
```

### Remotes Overview
- `conancenter`: Official Conan Center Index (`https://center2.conan.io`).
- `cura-conan2`: UltiMaker Open Source & Public Registry (`https://conan.ultimaker.com/api/packages/cura/conan`). Anonymous read access enabled worldwide.
- `cura-private-conan2`: UltiMaker Internal & Proprietary Registry (`https://conan.ultimaker.com/api/packages/cura-private/conan`). Disabled by default.

### Internal Developer Authentication
For internal packages in `cura-private-conan2`:
1. Enable the remote:
   ```bash
   conan remote enable cura-private-conan2
   ```
2. Log in with your UltiMaker SSO account or personal access token:
   ```bash
   conan remote login cura-private-conan2 <YOUR_GITEA_USERNAME> -p <YOUR_PERSONAL_ACCESS_TOKEN>
   ```
