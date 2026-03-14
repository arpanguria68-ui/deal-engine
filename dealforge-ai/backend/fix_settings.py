import re
import os

file_path = (
    r"f:\code project\Kimi_Agent_DealForge AI PRD\app\src\sections\SettingsPage.tsx"
)

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Fix the broken onChange and the missing wrapper
# We target the block between 'cfg?.key ?? \'\'' and 'placeholder={'

# Use a regex that is flexible with whitespace
pattern = re.compile(
    r"value=\{[\s\S]+?cfg\?\.key\s\?\?\s\'\'\s+\}\s+const\sval=\se\.target\.value;[\s\S]+?\}\s+placeholder=\{",
    re.MULTILINE,
)

replacement = """value={
                                                provider.id === 'serper' ? settings.serper_api_key :
                                                    provider.id === 'searxng' ? settings.searxng_instance_url :
                                                        provider.id === 'fmp' ? settings.fmp_api_key :
                                                            provider.id === 'alpha_vantage' ? settings.alpha_vantage_api_key :
                                                                provider.id === 'financial_datasets' ? settings.financial_datasets_api_key :
                                                                    provider.id === 'finnhub' ? settings.finnhub_api_key :
                                                                        provider.id === 'sec_api' ? settings.sec_api_key :
                                                                            mcpState[provider.id]?.key ?? ''
                                            }
                                            onChange={e => {
                                                const val = e.target.value;
                                                if (provider.id === 'serper') updateField('serper_api_key', val);
                                                else if (provider.id === 'searxng') updateField('searxng_instance_url', val);
                                                else if (provider.id === 'fmp') updateField('fmp_api_key', val);
                                                else if (provider.id === 'alpha_vantage') updateField('alpha_vantage_api_key', val);
                                                else if (provider.id === 'financial_datasets') updateField('financial_datasets_api_key', val);
                                                else if (provider.id === 'finnhub') updateField('finnhub_api_key', val);
                                                else if (provider.id === 'sec_api') updateField('sec_api_key', val);

                                                // Always update mcpState to enable the "Initialize & Test" button
                                                setMcpState(prev => ({
                                                    ...prev,
                                                    [provider.id]: { ...prev[provider.id], key: val, status: 'idle' },
                                                }));
                                            }}
                                            placeholder={"""

new_content = pattern.sub(replacement, content)

# 2. Fix the disabled logic on the button
# r'disabled=\{status === \'testing\' \|\| !cfg\?\.key\}'
new_content = new_content.replace(
    "disabled={status === 'testing' || !cfg?.key}",
    "disabled={status === 'testing' || !mcpState[provider.id]?.key}",
)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(new_content)

print("Success")
