'use client';

import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import i18n from '@/lib/i18n';
import { useTranslation } from 'react-i18next';

export default function Navbar() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [isManagementMenuOpen, setIsManagementMenuOpen] = useState(false);
  const [isLanguageMenuOpen, setIsLanguageMenuOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const managementMenuRef = useRef<HTMLDivElement>(null);
  const languageMenuRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const { t } = useTranslation('common');

  useEffect(() => {
    const token = localStorage.getItem('token');
    setIsLoggedIn(!!token);

    const handleLoginStatusChange = () => {
      setIsLoggedIn(!!localStorage.getItem('token'));
    }
    window.addEventListener('loginStatusChange', handleLoginStatusChange);
    return () => window.removeEventListener('loginStatusChange', handleLoginStatusChange);
  }, []);

  // Handle clicks outside of menus to close them
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (managementMenuRef.current && !managementMenuRef.current.contains(event.target as Node)) {
        setIsManagementMenuOpen(false);
      }
      if (languageMenuRef.current && !languageMenuRef.current.contains(event.target as Node)) {
        setIsLanguageMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('token');
    setIsLoggedIn(false);
    router.push('/login');
  };

  const changeLanguage = (lng: string) => {
    i18n.changeLanguage(lng);
    setIsLanguageMenuOpen(false);
    setIsMobileMenuOpen(false);
  };

  const closeAllMenus = () => {
    setIsManagementMenuOpen(false);
    setIsLanguageMenuOpen(false);
    setIsMobileMenuOpen(false);
  };

  return (
    <nav className="bg-white shadow-md border-b border-gray-200">
      <div className="container mx-auto flex items-center justify-between p-4">
        <div className="flex items-center space-x-8">
          <Link 
            href="/dashboard" 
            className="text-2xl font-bold text-indigo-700 hover:text-indigo-500 transition-colors duration-300 flex items-center"
            onClick={closeAllMenus}
          >
            <span className="bg-indigo-700 text-white rounded-lg px-2 py-1 mr-2 font-mono">AI</span>
            {t('common.aiGateway')}
          </Link>
          
          {/* Desktop Navigation */}
          <div className="hidden md:flex items-center space-x-1">
            {isLoggedIn && (
              <>
                <Link 
                  href="/dashboard" 
                  className="px-4 py-2 text-gray-700 hover:bg-indigo-50 rounded-lg transition-all duration-300"
                  onClick={closeAllMenus}
                >
                  {t('common.dashboard')}
                </Link>
                
                <Link 
                  href="/logs" 
                  className="px-4 py-2 text-gray-700 hover:bg-indigo-50 rounded-lg transition-all duration-300"
                  onClick={closeAllMenus}
                >
                  {t('common.logs')}
                </Link>
                
                <Link 
                  href="/users" 
                  className="px-4 py-2 text-gray-700 hover:bg-indigo-50 rounded-lg transition-all duration-300"
                  onClick={closeAllMenus}
                >
                  {t('common.users')}
                </Link>
                
                <div className="relative" ref={managementMenuRef}>
                  <button
                    className="px-4 py-2 text-gray-700 hover:bg-indigo-50 rounded-lg transition-all duration-300 flex items-center"
                    onClick={() => setIsManagementMenuOpen(!isManagementMenuOpen)}
                  >
                    {t('common.systemManagement')}
                    <svg className="ml-1 w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path>
                    </svg>
                  </button>
                  
                  {isManagementMenuOpen && (
                    <div className="absolute left-0 mt-1 w-48 bg-white rounded-lg shadow-xl py-2 z-20 animate-fadeIn border border-gray-200">
                      <Link 
                        href="/channels" 
                        className="block px-4 py-2 text-sm text-gray-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors duration-200"
                        onClick={closeAllMenus}
                      >
                        {t('common.channels')}
                      </Link>
                      <Link 
                        href="/keys" 
                        className="block px-4 py-2 text-sm text-gray-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors duration-200"
                        onClick={closeAllMenus}
                      >
                        {t('common.keys')}
                      </Link>
                      <Link 
                        href="/providers" 
                        className="block px-4 py-2 text-sm text-gray-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors duration-200"
                        onClick={closeAllMenus}
                      >
                        {t('common.providers')}
                      </Link>
                      <Link 
                        href="/models" 
                        className="block px-4 py-2 text-sm text-gray-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors duration-200"
                        onClick={closeAllMenus}
                      >
                        {t('common.models')}
                      </Link>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
        
        {/* Desktop Right Section */}
        <div className="hidden md:flex items-center space-x-4">
          <div className="relative" ref={languageMenuRef}>
            <button
              className="flex items-center text-gray-700 hover:bg-indigo-50 rounded-lg px-3 py-2 transition-all duration-300"
              onClick={() => setIsLanguageMenuOpen(!isLanguageMenuOpen)}
            >
              <svg className="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129"></path>
              </svg>
              {i18n.language === 'zh' ? t('language.chinese') : t('language.english')}
              <svg className="ml-1 w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path>
              </svg>
            </button>
            
            {isLanguageMenuOpen && (
              <div className="absolute right-0 mt-1 w-32 bg-white rounded-lg shadow-xl py-2 z-20 animate-fadeIn border border-gray-200">
                <button
                  className={`block px-4 py-2 text-sm w-full text-left transition-colors duration-200 ${
                    i18n.language === 'zh' 
                      ? 'bg-indigo-50 text-indigo-700' 
                      : 'text-gray-700 hover:bg-indigo-50 hover:text-indigo-700'
                  }`}
                  onClick={() => changeLanguage('zh')}
                >
                  {t('language.chinese')}
                </button>
                <button
                  className={`block px-4 py-2 text-sm w-full text-left transition-colors duration-200 ${
                    i18n.language === 'en' 
                      ? 'bg-indigo-50 text-indigo-700' 
                      : 'text-gray-700 hover:bg-indigo-50 hover:text-indigo-700'
                  }`}
                  onClick={() => changeLanguage('en')}
                >
                  {t('language.english')}
                </button>
              </div>
            )}
          </div>
          
          {isLoggedIn ? (
            <div className="flex items-center space-x-4">
              <Link 
                href="/profile"
                className="flex items-center text-gray-700 hover:bg-indigo-50 rounded-lg px-3 py-2 transition-all duration-300"
                onClick={closeAllMenus}
              >
                <svg className="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
                {t('common.profile', 'Profile')}
              </Link>
              <button 
                onClick={handleLogout} 
                className="flex items-center px-4 py-2 bg-rose-500 text-white font-medium rounded-lg hover:bg-rose-600 transition-all duration-300 shadow-sm hover:shadow-md"
              >
                <svg className="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path>
                </svg>
                {t('common.logout')}
              </button>
            </div>
          ) : (
            <Link 
              href="/login" 
              className="flex items-center px-4 py-2 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-all duration-300 shadow-sm hover:shadow-md"
            >
              <svg className="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1"></path>
              </svg>
              {t('common.login')}
            </Link>
          )}
        </div>
        
        {/* Mobile Menu Button */}
        <div className="md:hidden flex items-center">
          <button
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            className="text-gray-700 focus:outline-none"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              {isMobileMenuOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path>
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16"></path>
              )}
            </svg>
          </button>
        </div>
      </div>
      
      {/* Mobile Menu */}
      {isMobileMenuOpen && (
        <div className="md:hidden bg-white border-t border-gray-200 animate-slideDown">
          <div className="px-2 pt-2 pb-3 space-y-1 sm:px-3">
            {isLoggedIn ? (
              <>
                <Link 
                  href="/dashboard" 
                  className="block px-3 py-2 rounded-md text-base font-medium text-gray-700 hover:bg-indigo-50"
                  onClick={closeAllMenus}
                >
                  {t('common.dashboard')}
                </Link>
                
                <Link 
                  href="/logs" 
                  className="block px-3 py-2 rounded-md text-base font-medium text-gray-700 hover:bg-indigo-50"
                  onClick={closeAllMenus}
                >
                  {t('common.logs')}
                </Link>
                
                <Link 
                  href="/users" 
                  className="block px-3 py-2 rounded-md text-base font-medium text-gray-700 hover:bg-indigo-50"
                  onClick={closeAllMenus}
                >
                  {t('common.users')}
                </Link>
                
                <div className="border-t border-gray-200 pt-2">
                  <button
                    className="w-full text-left px-3 py-2 rounded-md text-base font-medium text-gray-700 hover:bg-indigo-50 flex justify-between items-center"
                    onClick={() => setIsManagementMenuOpen(!isManagementMenuOpen)}
                  >
                    <span>{t('common.systemManagement')}</span>
                    <svg 
                      className={`w-5 h-5 transform transition-transform ${isManagementMenuOpen ? 'rotate-180' : ''}`} 
                      fill="none" 
                      stroke="currentColor" 
                      viewBox="0 0 24 24" 
                      xmlns="http://www.w3.org/2000/svg"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path>
                    </svg>
                  </button>
                  
                  {isManagementMenuOpen && (
                    <div className="pl-4 space-y-1 mt-1">
                      <Link 
                        href="/channels" 
                        className="block px-3 py-2 rounded-md text-base font-medium text-gray-700 hover:bg-indigo-50"
                        onClick={closeAllMenus}
                      >
                        {t('common.channels')}
                      </Link>
                      <Link 
                        href="/keys" 
                        className="block px-3 py-2 rounded-md text-base font-medium text-gray-700 hover:bg-indigo-50"
                        onClick={closeAllMenus}
                      >
                        {t('common.keys')}
                      </Link>
                      <Link 
                        href="/providers" 
                        className="block px-3 py-2 rounded-md text-base font-medium text-gray-700 hover:bg-indigo-50"
                        onClick={closeAllMenus}
                      >
                        {t('common.providers')}
                      </Link>
                      <Link 
                        href="/models" 
                        className="block px-3 py-2 rounded-md text-base font-medium text-gray-700 hover:bg-indigo-50"
                        onClick={closeAllMenus}
                      >
                        {t('common.models')}
                      </Link>
                    </div>
                  )}
                </div>
                
                <div className="border-t border-gray-200 pt-2">
                  <button
                    className="w-full text-left px-3 py-2 rounded-md text-base font-medium text-gray-700 hover:bg-indigo-50 flex justify-between items-center"
                    onClick={() => setIsLanguageMenuOpen(!isLanguageMenuOpen)}
                  >
                    <span>
                      <svg className="w-5 h-5 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129"></path>
                      </svg>
                      {i18n.language === 'zh' ? t('language.chinese') : t('language.english')}
                    </span>
                    <svg 
                      className={`w-5 h-5 transform transition-transform ${isLanguageMenuOpen ? 'rotate-180' : ''}`} 
                      fill="none" 
                      stroke="currentColor" 
                      viewBox="0 0 24 24" 
                      xmlns="http://www.w3.org/2000/svg"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path>
                    </svg>
                  </button>
                  
                  {isLanguageMenuOpen && (
                    <div className="pl-4 space-y-1 mt-1">
                      <button
                        className={`block w-full text-left px-3 py-2 rounded-md text-base font-medium ${
                          i18n.language === 'zh' 
                            ? 'bg-indigo-50 text-indigo-700' 
                            : 'text-gray-700 hover:bg-indigo-50'
                        }`}
                        onClick={() => changeLanguage('zh')}
                      >
                        {t('language.chinese')}
                      </button>
                      <button
                        className={`block w-full text-left px-3 py-2 rounded-md text-base font-medium ${
                          i18n.language === 'en' 
                            ? 'bg-indigo-50 text-indigo-700' 
                            : 'text-gray-700 hover:bg-indigo-50'
                        }`}
                        onClick={() => changeLanguage('en')}
                      >
                        {t('language.english')}
                      </button>
                    </div>
                  )}
                </div>
                
                <div className="border-t border-gray-200 pt-2">
                  <Link 
                    href="/profile"
                    className="w-full flex items-center px-3 py-2 rounded-md text-base font-medium text-gray-700 hover:bg-indigo-50"
                    onClick={closeAllMenus}
                  >
                    <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
                    {t('common.profile', 'Profile')}
                  </Link>
                  <button 
                    onClick={handleLogout} 
                    className="w-full flex items-center px-3 py-2 rounded-md text-base font-medium text-gray-700 hover:bg-rose-50"
                  >
                    <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path>
                    </svg>
                    {t('common.logout')}
                  </button>
                </div>
              </>
            ) : (
              <Link 
                href="/login" 
                className="flex items-center px-3 py-2 rounded-md text-base font-medium text-gray-700 hover:bg-indigo-50"
                onClick={closeAllMenus}
              >
                <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1"></path>
                </svg>
                {t('common.login')}
              </Link>
            )}
          </div>
        </div>
      )}
    </nav>
  );
}
