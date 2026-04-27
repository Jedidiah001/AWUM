"""
Finance System
Calculates attendance, revenue, expenses, and profits for shows.
"""

import random
from typing import Dict, Any
from models.show import ShowDraft


class FinanceCalculator:
    """
    Handles all financial calculations for shows.
    
    Revenue sources:
    - Gate receipts (attendance × ticket price)
    - PPV buys (for PPV events)
    
    Expenses:
    - Wrestler payroll (per appearance)
    - Show production costs
    """
    
    # Base ticket prices
    TICKET_PRICES = {
        'weekly_tv': 35,
        'minor_ppv': 75,
        'major_ppv': 150
    }
    
    # Base attendance ranges
    BASE_ATTENDANCE = {
        'weekly_tv': (2000, 4000),
        'minor_ppv': (5000, 8000),
        'major_ppv': (12000, 18000)
    }
    
    # Production costs
    PRODUCTION_COSTS = {
        'weekly_tv': 50000,
        'minor_ppv': 150000,
        'major_ppv': 500000
    }
    
    def __init__(self):
        pass
    
    def calculate_attendance(
        self,
        show_draft: ShowDraft,
        brand_prestige: int = 50,
        current_balance: int = 1000000
    ) -> int:
        """
        Calculate attendance for a show.
        
        Factors:
        - Show type (PPV draws more)
        - Brand prestige
        - Main event star power
        - Time of year (peaks around major PPVs)
        - Financial health (affects marketing)
        """
        
        # Base attendance range
        min_att, max_att = self.BASE_ATTENDANCE.get(show_draft.show_type, (2000, 4000))
        base_attendance = random.randint(min_att, max_att)
        
        # Brand prestige modifier (-20% to +20%)
        prestige_modifier = ((brand_prestige - 50) / 50) * 0.2
        base_attendance = int(base_attendance * (1 + prestige_modifier))
        
        # Main event boost
        if show_draft.matches:
            main_event = show_draft.matches[-1]  # Last match is main event
            
            # If main event is a title match, boost attendance
            if main_event.is_title_match:
                base_attendance = int(base_attendance * 1.15)
            
            # If main event involves a feud, boost attendance
            if main_event.feud_id:
                base_attendance = int(base_attendance * 1.10)
        
        # Financial health modifier (poor finances = less marketing)
        if current_balance < 0:
            base_attendance = int(base_attendance * 0.85)
        elif current_balance > 5000000:
            base_attendance = int(base_attendance * 1.10)
        
        # Random variance ±10%
        variance = random.uniform(0.9, 1.1)
        final_attendance = int(base_attendance * variance)
        
        return max(500, final_attendance)  # Minimum 500 attendance
    
    def calculate_revenue(
        self,
        show_draft: ShowDraft,
        attendance: int
    ) -> Dict[str, int]:
        """
        Calculate total revenue for a show.
        
        Returns:
        - gate_revenue: Ticket sales
        - ppv_revenue: PPV buys (if applicable)
        - total_revenue: Sum of all revenue
        """
        
        ticket_price = self.TICKET_PRICES.get(show_draft.show_type, 35)
        gate_revenue = attendance * ticket_price
        
        ppv_revenue = 0
        
        # PPV buy calculations (major PPVs only)
        if show_draft.is_ppv and show_draft.show_type == 'major_ppv':
            # Estimate PPV buys (10-30% of attendance as buys)
            ppv_buys = int(attendance * random.uniform(0.10, 0.30))
            ppv_price = 49.99
            ppv_revenue = int(ppv_buys * ppv_price)
        
        return {
            'gate_revenue': gate_revenue,
            'ppv_revenue': ppv_revenue,
            'total_revenue': gate_revenue + ppv_revenue
        }
    
    def calculate_payroll(
        self,
        wrestlers_on_card: list  # List of Wrestler objects
    ) -> int:
        """
        Calculate total payroll for all wrestlers on the card.
        Each wrestler gets their salary_per_show.
        """
        total_payroll = 0
        
        for wrestler in wrestlers_on_card:
            total_payroll += wrestler.contract.salary_per_show
        
        return total_payroll
    
    def calculate_expenses(
        self,
        show_draft: ShowDraft,
        payroll: int
    ) -> Dict[str, int]:
        """
        Calculate all show expenses.
        
        Returns:
        - payroll: Wrestler salaries
        - production: Show production costs
        - total_expenses: Sum of all expenses
        """
        
        production_cost = self.PRODUCTION_COSTS.get(show_draft.show_type, 50000)
        
        return {
            'payroll': payroll,
            'production': production_cost,
            'total_expenses': payroll + production_cost
        }
    
    def calculate_net_profit(
        self,
        revenue: int,
        expenses: int
    ) -> int:
        """Calculate net profit/loss"""
        return revenue - expenses


# Global finance calculator instance
finance_calculator = FinanceCalculator()