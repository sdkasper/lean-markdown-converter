from setuptools import setup, find_packages

setup(
    name='markitdown',
    version='0.1.0',
    package_dir={'': 'src'},
    packages=find_packages(where='src'),
    install_requires=[
        'mammoth',
        'markdownify',
        'pandas',
        'pdfminer.six',
        'python-pptx',
        'puremagic',
        'requests',
        'beautifulsoup4',
        'pydub',
        'SpeechRecognition',
        'youtube_transcript_api',
    ],
    entry_points={
        'console_scripts': [
            'markitdown=markitdown.__main__:main',
        ],
    },
    author='Adam Fourney',
    author_email='adamfo@microsoft.com',
    description='Convert various file formats to markdown',
    license='MIT',
    python_requires='>=3.6',
)