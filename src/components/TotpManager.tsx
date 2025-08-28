'use client';

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import Image from 'next/image';

const TotpManager = () => {
  const { t } = useTranslation();
  const [totpEnabled, setTotpEnabled] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [setupInfo, setSetupInfo] = useState<{ secret: string; qrCodeDataUrl: string } | null>(null);
  const [verificationToken, setVerificationToken] = useState('');
  const [disablePassword, setDisablePassword] = useState('');

  const fetchUserStatus = async () => {
    setIsLoading(true);
    try {
      const response = await fetch('/api/users/me', {
        headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` },
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      setTotpEnabled(data.totpEnabled);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchUserStatus();
  }, []);

  const handleEnable = async () => {
    setIsLoading(true);
    setError('');
    try {
      const response = await fetch('/api/users/me/totp/setup', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` },
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      setSetupInfo(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    try {
      const response = await fetch('/api/users/me/totp/verify', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
        body: JSON.stringify({ token: verificationToken }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      setTotpEnabled(true);
      setSetupInfo(null);
      setVerificationToken('');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDisable = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    try {
      const response = await fetch('/api/users/me/totp/disable', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
        body: JSON.stringify({ password: disablePassword }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      setTotpEnabled(false);
      setDisablePassword('');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading && !setupInfo) {
    return <div>{t('common.loading', 'Loading...')}</div>;
  }

  return (
    <div className="p-4 border rounded-lg bg-white dark:bg-gray-800">
      <h3 className="text-lg font-semibold mb-2">{t('profile.security.totp.title', 'Two-Factor Authentication (TOTP)')}</h3>
      {error && <p className="text-sm text-red-600 mb-4">{error}</p>}

      {totpEnabled ? (
        <div>
          <p className="text-sm text-green-600 mb-4">{t('profile.security.totp.status.enabled', 'Two-factor authentication is enabled.')}</p>
          <form onSubmit={handleDisable} className="space-y-4">
            <div>
              <label className="block text-sm font-medium" htmlFor="disable-password">{t('profile.security.totp.disable.passwordPrompt', 'Enter your password to disable')}</label>
              <input
                id="disable-password"
                type="password"
                value={disablePassword}
                onChange={(e) => setDisablePassword(e.target.value)}
                className="mt-1 block w-full sm:w-1/2 px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm"
                required
              />
            </div>
            <button type="submit" disabled={isLoading} className="py-2 px-4 text-sm font-medium rounded-md text-white bg-red-600 hover:bg-red-700 disabled:opacity-50">
              {isLoading ? t('common.loading', 'Loading...') : t('profile.security.totp.disable.button', 'Disable TOTP')}
            </button>
          </form>
        </div>
      ) : setupInfo ? (
        <div>
          <p className="mb-2">{t('profile.security.totp.setup.scan', 'Scan the QR code with your authenticator app.')}</p>
          <Image src={setupInfo.qrCodeDataUrl} alt="TOTP QR Code" width={200} height={200} />
          <p className="mt-2 text-sm">{t('profile.security.totp.setup.manual', 'Or enter this code manually:')}</p>
          <code className="block bg-gray-100 dark:bg-gray-700 p-2 rounded my-2">{setupInfo.secret}</code>
          <form onSubmit={handleVerify} className="space-y-4 mt-4">
            <div>
              <label className="block text-sm font-medium" htmlFor="verification-token">{t('profile.security.totp.setup.enterToken', 'Enter the token from your app')}</label>
              <input
                id="verification-token"
                type="text"
                value={verificationToken}
                onChange={(e) => setVerificationToken(e.target.value)}
                className="mt-1 block w-full sm:w-1/2 px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm"
                required
              />
            </div>
            <button type="submit" disabled={isLoading} className="py-2 px-4 text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50">
              {isLoading ? t('common.loading', 'Loading...') : t('profile.security.totp.setup.verifyButton', 'Verify & Enable')}
            </button>
          </form>
        </div>
      ) : (
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{t('profile.security.totp.status.disabled', 'Two-factor authentication is not enabled.')}</p>
          <button onClick={handleEnable} disabled={isLoading} className="py-2 px-4 text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50">
            {isLoading ? t('common.loading', 'Loading...') : t('profile.security.totp.enableButton', 'Enable TOTP')}
          </button>
        </div>
      )}
    </div>
  );
};

export default TotpManager;
