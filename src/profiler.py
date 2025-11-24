#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database Performance Profiler
Analyzes slow queries and recommends indexes
"""

import psycopg2
import time
import re
from datetime import datetime
from typing import List, Dict, Tuple
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DatabaseProfiler:
    """Profiles database performance and suggests optimizations"""
    
    def __init__(self, conn_params: Dict):
        self.conn_params = conn_params
        self.conn = None
        self.slow_queries = []
        self.recommendations = []
        
    def connect(self):
        """Connect to database"""
        try:
            self.conn = psycopg2.connect(**self.conn_params)
            self.conn.autocommit = True
            logger.info(f"Connected to database: {self.conn_params['dbname']}")
            return True
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    def setup_demo_data(self):
        """Create demo tables and data"""
        logger.info("Setting up demo data...")
        
        cursor = self.conn.cursor()
        
        # Create tables
        cursor.execute("""
            DROP TABLE IF EXISTS orders CASCADE;
            DROP TABLE IF EXISTS customers CASCADE;
            DROP TABLE IF EXISTS products CASCADE;
            
            CREATE TABLE customers (
                customer_id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                email VARCHAR(100),
                city VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW()
            );
            
            CREATE TABLE products (
                product_id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                category VARCHAR(50),
                price DECIMAL(10,2),
                stock INT
            );
            
            CREATE TABLE orders (
                order_id SERIAL PRIMARY KEY,
                customer_id INT,
                product_id INT,
                quantity INT,
                order_date TIMESTAMP DEFAULT NOW(),
                status VARCHAR(20)
            );
        """)
        
        # Insert demo data
        logger.info("Inserting 10,000 customers...")
        cursor.execute("""
            INSERT INTO customers (name, email, city)
            SELECT 
                'Customer ' || i,
                'customer' || i || '@example.com',
                CASE (i % 5)
                    WHEN 0 THEN 'New York'
                    WHEN 1 THEN 'Los Angeles'
                    WHEN 2 THEN 'Chicago'
                    WHEN 3 THEN 'Houston'
                    ELSE 'Phoenix'
                END
            FROM generate_series(1, 10000) i;
        """)
        
        logger.info("Inserting 1,000 products...")
        cursor.execute("""
            INSERT INTO products (name, category, price, stock)
            SELECT 
                'Product ' || i,
                CASE (i % 4)
                    WHEN 0 THEN 'Electronics'
                    WHEN 1 THEN 'Clothing'
                    WHEN 2 THEN 'Food'
                    ELSE 'Books'
                END,
                (random() * 1000)::DECIMAL(10,2),
                (random() * 1000)::INT
            FROM generate_series(1, 1000) i;
        """)
        
        logger.info("Inserting 50,000 orders...")
        cursor.execute("""
            INSERT INTO orders (customer_id, product_id, quantity, order_date, status)
            SELECT 
                (random() * 9999 + 1)::INT,
                (random() * 999 + 1)::INT,
                (random() * 10 + 1)::INT,
                NOW() - (random() * 365 || ' days')::INTERVAL,
                CASE (random() * 3)::INT
                    WHEN 0 THEN 'pending'
                    WHEN 1 THEN 'completed'
                    ELSE 'cancelled'
                END
            FROM generate_series(1, 50000);
        """)
        
        cursor.close()
        logger.info("Demo data created successfully!")
    
    def analyze_query(self, query: str) -> Dict:
        """Analyze query execution plan"""
        cursor = self.conn.cursor()
        
        # Get execution plan
        explain_query = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"
        
        start_time = time.time()
        try:
            cursor.execute(explain_query)
            plan = cursor.fetchone()[0][0]
            execution_time = time.time() - start_time
            
            # Extract key metrics
            total_cost = plan['Plan']['Total Cost']
            actual_time = plan['Plan']['Actual Total Time']
            rows = plan['Plan']['Actual Rows']
            
            # Check for sequential scans
            seq_scans = self._find_seq_scans(plan['Plan'])
            
            analysis = {
                'query': query[:100] + '...' if len(query) > 100 else query,
                'execution_time_ms': round(actual_time, 2),
                'total_cost': round(total_cost, 2),
                'rows_returned': rows,
                'sequential_scans': seq_scans,
                'timestamp': datetime.now().isoformat()
            }
            
            cursor.close()
            return analysis
            
        except Exception as e:
            logger.error(f"Query analysis failed: {e}")
            cursor.close()
            return {'error': str(e)}
    
    def _find_seq_scans(self, plan: Dict, scans: List = None) -> List:
        """Recursively find sequential scans in plan"""
        if scans is None:
            scans = []
        
        if plan.get('Node Type') == 'Seq Scan':
            scans.append({
                'table': plan.get('Relation Name'),
                'rows': plan.get('Actual Rows'),
                'time': plan.get('Actual Total Time')
            })
        
        # Check child plans
        if 'Plans' in plan:
            for child_plan in plan['Plans']:
                self._find_seq_scans(child_plan, scans)
        
        return scans
    
    def recommend_indexes(self, analysis: Dict) -> List[str]:
        """Recommend indexes based on analysis"""
        recommendations = []
        
        # Recommend indexes for sequential scans
        for scan in analysis.get('sequential_scans', []):
            if scan['rows'] > 1000:  # Only recommend if scanning many rows
                table = scan['table']
                recommendations.append(
                    f"CREATE INDEX idx_{table}_lookup ON {table} (column_name); "
                    f"-- Seq scan on {table} accessed {scan['rows']:,} rows"
                )
        
        return recommendations
    
    def run_slow_queries(self) -> List[Dict]:
        """Execute intentionally slow queries for demo"""
        logger.info("Running performance tests...")
        
        slow_queries = [
            # Query 1: Full table scan without index
            """
            SELECT c.name, c.email, COUNT(o.order_id) as order_count
            FROM customers c
            LEFT JOIN orders o ON c.customer_id = o.customer_id
            WHERE c.city = 'New York'
            GROUP BY c.customer_id, c.name, c.email
            ORDER BY order_count DESC
            LIMIT 10;
            """,
            
            # Query 2: Join without indexes
            """
            SELECT p.name, p.category, COUNT(o.order_id) as times_ordered
            FROM products p
            JOIN orders o ON p.product_id = o.product_id
            WHERE o.status = 'completed'
            GROUP BY p.product_id, p.name, p.category
            ORDER BY times_ordered DESC
            LIMIT 20;
            """,
            
            # Query 3: Complex aggregation
            """
            SELECT 
                DATE_TRUNC('month', o.order_date) as month,
                p.category,
                COUNT(*) as order_count,
                SUM(o.quantity * p.price) as revenue
            FROM orders o
            JOIN products p ON o.product_id = p.product_id
            WHERE o.status IN ('completed', 'pending')
            GROUP BY month, p.category
            ORDER BY month DESC, revenue DESC;
            """,
        ]
        
        results = []
        
        for i, query in enumerate(slow_queries, 1):
            logger.info(f"Analyzing query {i}/3...")
            
            analysis = self.analyze_query(query)
            
            if 'error' not in analysis:
                recommendations = self.recommend_indexes(analysis)
                analysis['recommendations'] = recommendations
                results.append(analysis)
                
                # Print results
                print("\n" + "=" * 80)
                print(f"QUERY {i} ANALYSIS")
                print("=" * 80)
                print(f"Query: {analysis['query']}")
                print(f"\nPerformance Metrics:")
                print(f"  Execution Time: {analysis['execution_time_ms']:.2f} ms")
                print(f"  Total Cost: {analysis['total_cost']:.2f}")
                print(f"  Rows Returned: {analysis['rows_returned']:,}")
                
                if analysis['sequential_scans']:
                    print(f"\nSequential Scans Found:")
                    for scan in analysis['sequential_scans']:
                        print(f"  - Table: {scan['table']}")
                        print(f"    Rows Scanned: {scan['rows']:,}")
                        print(f"    Time: {scan['time']:.2f} ms")
                
                if recommendations:
                    print(f"\nRecommendations:")
                    for rec in recommendations:
                        print(f"  {rec}")
                
                print("=" * 80)
        
        return results
    
    def apply_optimizations(self):
        """Apply recommended indexes"""
        logger.info("Applying optimizations...")
        
        cursor = self.conn.cursor()
        
        optimizations = [
            "CREATE INDEX idx_customers_city ON customers(city);",
            "CREATE INDEX idx_orders_customer_id ON orders(customer_id);",
            "CREATE INDEX idx_orders_product_id ON orders(product_id);",
            "CREATE INDEX idx_orders_status ON orders(status);",
            "CREATE INDEX idx_orders_date ON orders(order_date);",
            "CREATE INDEX idx_products_category ON products(category);",
        ]
        
        for opt in optimizations:
            try:
                cursor.execute(opt)
                logger.info(f"Applied: {opt}")
            except Exception as e:
                logger.warning(f"Failed to apply {opt}: {e}")
        
        cursor.close()
        logger.info("Optimizations applied!")
    
    def run_benchmark(self):
        """Run complete benchmark"""
        print("\n" + "=" * 80)
        print("DATABASE PERFORMANCE PROFILER - BENCHMARK")
        print("=" * 80)
        
        # Setup
        if not self.connect():
            return
        
        self.setup_demo_data()
        
        # Test 1: Before optimization
        print("\n" + "=" * 80)
        print("PHASE 1: ANALYZING PERFORMANCE (BEFORE OPTIMIZATION)")
        print("=" * 80)
        results_before = self.run_slow_queries()
        
        # Apply optimizations
        print("\n" + "=" * 80)
        print("PHASE 2: APPLYING OPTIMIZATIONS")
        print("=" * 80)
        self.apply_optimizations()
        
        # Test 2: After optimization
        print("\n" + "=" * 80)
        print("PHASE 3: RE-ANALYZING PERFORMANCE (AFTER OPTIMIZATION)")
        print("=" * 80)
        results_after = self.run_slow_queries()
        
        # Summary
        print("\n" + "=" * 80)
        print("PERFORMANCE IMPROVEMENT SUMMARY")
        print("=" * 80)
        
        for i in range(min(len(results_before), len(results_after))):
            before = results_before[i]['execution_time_ms']
            after = results_after[i]['execution_time_ms']
            improvement = ((before - after) / before * 100) if before > 0 else 0
            
            print(f"\nQuery {i+1}:")
            print(f"  Before: {before:.2f} ms")
            print(f"  After:  {after:.2f} ms")
            print(f"  Improvement: {improvement:.1f}%")
        
        print("\n" + "=" * 80)
        print("BENCHMARK COMPLETE!")
        print("=" * 80)


def main():
    """Main entry point"""
    
    conn_params = {
        'host': 'localhost',
        'port': 5438,
        'dbname': 'perftest',
        'user': 'postgres',
        'password': 'postgres'
    }
    
    profiler = DatabaseProfiler(conn_params)
    profiler.run_benchmark()


if __name__ == "__main__":
    main()
