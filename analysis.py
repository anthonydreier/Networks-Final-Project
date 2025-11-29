import pandas as pd
from datetime import datetime
import time
import threading
import json
import os
from typing import Dict, List, Optional

class NetworkAnalysisModule:
    def __init__(self, source: str='unspecified', verbose: bool=True):
        '''
        Purpose: Initialize NetworkAnalysisModule object and its attributes

        Parameters:
            source: Specifies origin of object call (e.g. 'client' or 'server')
            verbose: Whether statements are printed to console
        '''
        self.metrics: List[Dict] = [] # e.g. [{'action': 'upload', 'filename': 'example.txt', ...}, ...]
        self.metrics_lock = threading.Lock()  # Protect metrics from race conditions

        self.start_time = time.time()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Set reports directory and mkdir if it doesn't exist
        self.report_folder = "Analysis Reports"
        if not os.path.exists(self.report_folder):
            os.makedirs(self.report_folder)

        self.json_file = os.path.join(self.report_folder, f"{source}_metrics_{timestamp}.json")
        self.csv_file = os.path.join(self.report_folder, f"{source}_metrics_{timestamp}.csv")

        self.source = source
        self.verbose = verbose

        if self.verbose:
            print(f"[ANALYSIS] {source.upper()} analysis started. Metrics will be saved to {self.json_file}") # DEBUG
    
    def record_action(self, action_type: str, filename: str, file_size: int, duration: float, client_id: str, status: str="success"):
        """
        Purpose: Record an interaction between client and server along with metrics
        
        Parameters:
            action_type: Type of action (e.g. upload, download, delete, dir, subfolder)
            filename: Name of file being transferred
            file_size: Size of file (in bytes)
            duration: Time taken for action (in seconds)
            client_id: Client indentifier
            status: Success or failure status
        """
        # Calculate transfer rate (MB/sec)
        if duration > 0:
            transfer_rate_mbps = (file_size / (2**20)) / duration
        else:
            transfer_rate_mbps = 0

        # Dict of metrics for the particular action
        metric = {
            'timestamp': datetime.now().isoformat(),
            'action': action_type,
            'filename': filename,
            'file_size_bytes': file_size,
            'file_size_mb': round(file_size / (2**20), 4),
            'duration_seconds': round(duration, 4),
            'transfer_rate_mbps': round(transfer_rate_mbps, 4),
            'client_id': client_id,
            'status': status,
            'system_uptime': round(time.time() - self.start_time, 2)
        }
        
        # Acquire lock and insert metric
        with self.metrics_lock:
            self.metrics.append(metric)
            if len(self.metrics) % 10 == 0: # Save for every 10 actions (unsafe, as lock is already obtained)
                self._save_metrics_unsafe()
        
        if self.verbose:
            print(f"[ANALYSIS] Recorded {action_type}: {filename} ({transfer_rate_mbps:.2f} MB/s, {duration:.2f}s)")
    
    def record_connection(self, client_id: str, event_type: str, response_time: Optional[float]=None):
        """
        Purpose: Record connection event
        
        Parameters:
            client_id: Identifier for the client
            event_type: Type of event (connect, disconnect, auth_success, auth_fail)
            response_time: System response time for authentication
        """
        # Dict of metrics for connection
        metric = {
            'timestamp': datetime.now().isoformat(),
            'action': event_type,
            'filename': None,
            'file_size_bytes': 0,
            'file_size_mb': 0,
            'duration_seconds': round(response_time, 4) if response_time else 0,
            'transfer_rate_mbps': 0,
            'client_id': client_id,
            'status': 'success' if 'success' in event_type else 'info',
            'system_uptime': round(time.time() - self.start_time, 2)
        }
        
        # Acquire lock and insert metric
        with self.metrics_lock:
            self.metrics.append(metric)
        
        if self.verbose:
            print(f"[ANALYSIS] Recorded {event_type}: {client_id}")
    
    def _save_metrics_unsafe(self):
        """
        Purpose: Save metrics to JSON and CSV results files. Must be holding metrics_lock.
        """
        try:
            # Save as JSON
            with open(self.json_file, 'w') as f:
                json.dump(self.metrics, f, indent=2)
            
            # Save as CSV
            if self.metrics:
                df = pd.DataFrame(self.metrics)
                df.to_csv(self.csv_file, index=False)
        except Exception as e:
            if self.verbose:
                print(f"[ANALYSIS] Error saving metrics: {e}")
    
    def save_metrics(self):
        """
        Purpose: Save metrics to JSON and CSV results files. Not required to hold metrics_lock before calling.
        """
        # Acquire lock and save metrics (safe)
        with self.metrics_lock:
            self._save_metrics_unsafe()
        if self.verbose:
            print(f"[ANALYSIS] Metrics saved to {self.json_file} and {self.csv_file}")
    
    def get_statistics(self):
        """
        Purpose: Generate statistics from current metrics
        
        Returns:
            stats: Dictionary holding statistics
        """
        # Acquire lock and copy metrics
        with self.metrics_lock:
            if not self.metrics:
                return {"error": "No metrics collected yet"}
            metrics_copy = self.metrics.copy()
        
        df = pd.DataFrame(metrics_copy)
        
        # Filter for file transfer actions
        transfer_actions = df[df['action'].isin(['upload', 'download'])]
        
        stats = {
            'total_actions': len(df),
            'successful_actions': len(df[df['status'] == 'success']),
            'failed_actions': len(df[df['status'] == 'failure']),
            'system_uptime_seconds': round(time.time() - self.start_time, 2)
        }
        
        if not transfer_actions.empty:
            # Upload statistics
            uploads = transfer_actions[transfer_actions['action'] == 'upload']
            if not uploads.empty:
                stats['upload_stats'] = {
                    'count': len(uploads),
                    'avg_rate_mbps': round(uploads['transfer_rate_mbps'].mean(), 4),
                    'max_rate_mbps': round(uploads['transfer_rate_mbps'].max(), 4),
                    'min_rate_mbps': round(uploads['transfer_rate_mbps'].min(), 4),
                    'avg_transfer_time': round(uploads['duration_seconds'].mean(), 4),
                    'total_data_mb': round(uploads['file_size_mb'].sum(), 2)
                }
            
            # Download statistics
            downloads = transfer_actions[transfer_actions['action'] == 'download']
            if not downloads.empty:
                stats['download_stats'] = {
                    'count': len(downloads),
                    'avg_rate_mbps': round(downloads['transfer_rate_mbps'].mean(), 4),
                    'max_rate_mbps': round(downloads['transfer_rate_mbps'].max(), 4),
                    'min_rate_mbps': round(downloads['transfer_rate_mbps'].min(), 4),
                    'avg_transfer_time': round(downloads['duration_seconds'].mean(), 4),
                    'total_data_mb': round(downloads['file_size_mb'].sum(), 2)
                }
            
            # Overall transfer statistics
            stats['overall_transfer_stats'] = {
                'avg_rate_mbps': round(transfer_actions['transfer_rate_mbps'].mean(), 4),
                'total_data_transferred_mb': round(transfer_actions['file_size_mb'].sum(), 2),
                'avg_transfer_time': round(transfer_actions['duration_seconds'].mean(), 4)
            }
        
        # Authentication statistics
        connections = df[df['action'].isin(['connect', 'auth_success', 'auth_fail'])]
        if not connections.empty:
            auth_ops = connections[connections['action'].isin(['auth_success', 'auth_fail'])]
            if not auth_ops.empty:
                stats['authentication_stats'] = {
                    'total_attempts': len(auth_ops),
                    'successful': len(auth_ops[auth_ops['action'] == 'auth_success']),
                    'failed': len(auth_ops[auth_ops['action'] == 'auth_fail']),
                    'avg_response_time': round(auth_ops['duration_seconds'].mean(), 4)
                }
        
        return stats
    
    def generate_report_txt(self):
        """
        Purpose: Generate a .txt report of statistics
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"{self.source}_report_{timestamp}.txt"
        
        # If file path is not absolute, prepend report folder
        if not os.path.isabs(output_file):
            output_file = os.path.join(self.report_folder, output_file)

        stats = self.get_statistics()
        
        # Write results to .txt file
        with open(output_file, 'w') as f:
            f.write(f"-- {self.source.upper()} ANALYSIS REPORT --\n")
            f.write(f"Report Source: {self.source.upper()}\n")
            f.write(f"Report Generated: {timestamp}\n")
            f.write(f"System Uptime: {stats.get('system_uptime_seconds', 0):.2f} seconds\n\n\n")
            
            f.write("-- ACTION SUMMARY --\n")
            f.write(f"Total Actions: {stats.get('total_actions', 0)}\n")
            f.write(f"Successful: {stats.get('successful_actions', 0)}\n")
            f.write(f"Failed: {stats.get('failed_actions', 0)}\n\n\n")
            
            if 'upload_stats' in stats:
                f.write("-- UPLOAD SUMMARY --\n")
                us = stats['upload_stats']
                f.write(f"Number of Uploads: {us['count']}\n")
                f.write(f"Average Upload Rate: {us['avg_rate_mbps']:.4f} MB/sec\n")
                f.write(f"Maximum Upload Rate: {us['max_rate_mbps']:.4f} MB/sec\n")
                f.write(f"Minimum Upload Rate: {us['min_rate_mbps']:.4f} MB/sec\n")
                f.write(f"Average Transfer Time: {us['avg_transfer_time']:.4f} seconds\n")
                f.write(f"Total Data Uploaded: {us['total_data_mb']:.2f} MB\n\n\n")
            
            if 'download_stats' in stats:
                f.write("-- DOWNLOAD SUMMARY --\n")
                ds = stats['download_stats']
                f.write(f"Number of Downloads: {ds['count']}\n")
                f.write(f"Average Download Rate: {ds['avg_rate_mbps']:.4f} MB/sec\n")
                f.write(f"Maximum Download Rate: {ds['max_rate_mbps']:.4f} MB/sec\n")
                f.write(f"Minimum Download Rate: {ds['min_rate_mbps']:.4f} MB/sec\n")
                f.write(f"Average Transfer Time: {ds['avg_transfer_time']:.4f} seconds\n")
                f.write(f"Total Data Downloaded: {ds['total_data_mb']:.2f} MB\n\n\n")
            
            if 'authentication_stats' in stats:
                f.write("-- AUTHENTICATION SUMMARY --\n")
                aus = stats['authentication_stats']
                f.write(f"Total Auth Attempts: {aus['total_attempts']}\n")
                f.write(f"Successful: {aus['successful']}\n")
                f.write(f"Failed: {aus['failed']}\n")
                f.write(f"Average Response Time: {aus['avg_response_time']:.4f} seconds")
        
        if self.verbose:
            print(f"[Analyzer] Report generated: {output_file}")

        return output_file
    
    def stop(self):
        """
        Purpose: Save metrics and generate final .txt report
        """
        self.save_metrics()
        self.generate_report_txt()