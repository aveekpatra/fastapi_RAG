"""
Quick Fixes for Wrong Search Results
Apply common fixes without manually editing code
"""
import os
import re
from pathlib import Path


def backup_file(filepath: str):
    """Create a backup of the file"""
    backup_path = f"{filepath}.backup"
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Backup created: {backup_path}")
        return True
    return False


def apply_fix_1_use_max_score():
    """
    Fix 1: Use max score instead of weighted scoring
    This is the most conservative approach - uses the highest score from any query
    """
    print("\n" + "=" * 80)
    print("FIX 1: Use Max Score Instead of Weighted Scoring")
    print("=" * 80)
    print("\nThis will change the scoring formula to use the maximum score")
    print("from any query instead of weighted average.")
    print("\nPros: More conservative, favors highest relevance")
    print("Cons: Ignores frequency information")
    
    confirm = input("\nApply this fix? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Skipped.")
        return
    
    filepath = "app/services/qdrant.py"
    
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return
    
    backup_file(filepath)
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find and replace the weighted scoring line
    old_pattern = r"weighted_score = \(data\['total_score'\] / data\['count'\]\) \* \(data\['count'\] \*\* 0\.5\)"
    new_code = "weighted_score = data['max_score']  # Using max score (applied by quick_fixes.py)"
    
    if re.search(old_pattern, content):
        content = re.sub(old_pattern, new_code, content)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Fix applied successfully!")
        print(f"   Modified: {filepath}")
        print("   Restart your API server for changes to take effect.")
    else:
        print("⚠️  Could not find the scoring formula to replace.")
        print("   The code might have been modified already.")


def apply_fix_2_use_average_score():
    """
    Fix 2: Use average score without frequency bonus
    Balanced approach - uses average score across queries
    """
    print("\n" + "=" * 80)
    print("FIX 2: Use Average Score Without Frequency Bonus")
    print("=" * 80)
    print("\nThis will change the scoring formula to use simple average")
    print("without giving bonus to cases appearing in multiple queries.")
    print("\nPros: Balanced, considers all queries equally")
    print("Cons: Doesn't reward cases found by multiple queries")
    
    confirm = input("\nApply this fix? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Skipped.")
        return
    
    filepath = "app/services/qdrant.py"
    
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return
    
    backup_file(filepath)
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find and replace the weighted scoring line
    old_pattern = r"weighted_score = \(data\['total_score'\] / data\['count'\]\) \* \(data\['count'\] \*\* 0\.5\)"
    new_code = "weighted_score = data['total_score'] / data['count']  # Using average score (applied by quick_fixes.py)"
    
    if re.search(old_pattern, content):
        content = re.sub(old_pattern, new_code, content)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Fix applied successfully!")
        print(f"   Modified: {filepath}")
        print("   Restart your API server for changes to take effect.")
    else:
        print("⚠️  Could not find the scoring formula to replace.")
        print("   The code might have been modified already.")


def apply_fix_3_reduce_frequency_bonus():
    """
    Fix 3: Reduce frequency bonus
    Keeps weighted scoring but reduces the frequency impact
    """
    print("\n" + "=" * 80)
    print("FIX 3: Reduce Frequency Bonus")
    print("=" * 80)
    print("\nThis will reduce the frequency bonus from sqrt(count) to count^0.3")
    print("This gives less weight to cases appearing in multiple queries.")
    print("\nPros: Still rewards frequency but less aggressively")
    print("Cons: Might still favor wrong answers if queries are bad")
    
    confirm = input("\nApply this fix? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Skipped.")
        return
    
    filepath = "app/services/qdrant.py"
    
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return
    
    backup_file(filepath)
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find and replace the weighted scoring line
    old_pattern = r"weighted_score = \(data\['total_score'\] / data\['count'\]\) \* \(data\['count'\] \*\* 0\.5\)"
    new_code = "weighted_score = (data['total_score'] / data['count']) * (data['count'] ** 0.3)  # Reduced frequency bonus (applied by quick_fixes.py)"
    
    if re.search(old_pattern, content):
        content = re.sub(old_pattern, new_code, content)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Fix applied successfully!")
        print(f"   Modified: {filepath}")
        print("   Restart your API server for changes to take effect.")
    else:
        print("⚠️  Could not find the scoring formula to replace.")
        print("   The code might have been modified already.")


def apply_fix_4_disable_improved_rag():
    """
    Fix 4: Disable improved RAG entirely
    Falls back to basic single-query search
    """
    print("\n" + "=" * 80)
    print("FIX 4: Disable Improved RAG")
    print("=" * 80)
    print("\nThis will disable improved RAG and use basic single-query search.")
    print("\nPros: Simple, reliable, no query generation overhead")
    print("Cons: Might miss relevant cases that multi-query would find")
    
    confirm = input("\nApply this fix? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Skipped.")
        return
    
    env_file = ".env"
    
    if not os.path.exists(env_file):
        print(f"❌ File not found: {env_file}")
        return
    
    backup_file(env_file)
    
    with open(env_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    modified = False
    new_lines = []
    
    for line in lines:
        if line.strip().startswith('USE_IMPROVED_RAG'):
            new_lines.append('USE_IMPROVED_RAG=False\n')
            modified = True
        else:
            new_lines.append(line)
    
    if not modified:
        # Add the setting if it doesn't exist
        new_lines.append('\n# Disable improved RAG (applied by quick_fixes.py)\n')
        new_lines.append('USE_IMPROVED_RAG=False\n')
        modified = True
    
    if modified:
        with open(env_file, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        print("✅ Fix applied successfully!")
        print(f"   Modified: {env_file}")
        print("   Restart your API server for changes to take effect.")
    else:
        print("⚠️  Could not modify .env file")


def apply_fix_5_reduce_num_queries():
    """
    Fix 5: Reduce number of generated queries
    Generates fewer queries to reduce noise
    """
    print("\n" + "=" * 80)
    print("FIX 5: Reduce Number of Generated Queries")
    print("=" * 80)
    print("\nThis will reduce the number of generated queries from 3 to 2.")
    print("\nPros: Less noise, faster, more focused")
    print("Cons: Might miss some relevant cases")
    
    confirm = input("\nApply this fix? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Skipped.")
        return
    
    env_file = ".env"
    
    if not os.path.exists(env_file):
        print(f"❌ File not found: {env_file}")
        return
    
    backup_file(env_file)
    
    with open(env_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    modified = False
    new_lines = []
    
    for line in lines:
        if line.strip().startswith('NUM_GENERATED_QUERIES'):
            new_lines.append('NUM_GENERATED_QUERIES=2\n')
            modified = True
        else:
            new_lines.append(line)
    
    if not modified:
        # Add the setting if it doesn't exist
        new_lines.append('\n# Reduce number of queries (applied by quick_fixes.py)\n')
        new_lines.append('NUM_GENERATED_QUERIES=2\n')
        modified = True
    
    if modified:
        with open(env_file, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        print("✅ Fix applied successfully!")
        print(f"   Modified: {env_file}")
        print("   Restart your API server for changes to take effect.")
    else:
        print("⚠️  Could not modify .env file")


def restore_backups():
    """
    Restore all backup files
    """
    print("\n" + "=" * 80)
    print("RESTORE BACKUPS")
    print("=" * 80)
    
    backup_files = list(Path('.').rglob('*.backup'))
    
    if not backup_files:
        print("No backup files found.")
        return
    
    print(f"\nFound {len(backup_files)} backup file(s):")
    for backup in backup_files:
        print(f"  - {backup}")
    
    confirm = input("\nRestore all backups? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return
    
    for backup in backup_files:
        original = str(backup).replace('.backup', '')
        
        with open(backup, 'r', encoding='utf-8') as f:
            content = f.read()
        
        with open(original, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Restored: {original}")
    
    print("\n✅ All backups restored!")
    print("   Restart your API server for changes to take effect.")


def main():
    """Main menu"""
    print("\n" + "=" * 80)
    print("QUICK FIXES FOR WRONG SEARCH RESULTS")
    print("=" * 80)
    print("\nThis tool applies common fixes to improve search results.")
    print("Backups are created automatically before making changes.")
    
    while True:
        print("\n" + "-" * 80)
        print("Available fixes:")
        print("-" * 80)
        print("1. Use max score (most conservative)")
        print("2. Use average score (balanced)")
        print("3. Reduce frequency bonus (moderate)")
        print("4. Disable improved RAG (fallback to basic)")
        print("5. Reduce number of queries (less noise)")
        print("6. Restore all backups")
        print("0. Exit")
        
        choice = input("\nSelect a fix (0-6): ").strip()
        
        if choice == '0':
            print("\nExiting...")
            break
        elif choice == '1':
            apply_fix_1_use_max_score()
        elif choice == '2':
            apply_fix_2_use_average_score()
        elif choice == '3':
            apply_fix_3_reduce_frequency_bonus()
        elif choice == '4':
            apply_fix_4_disable_improved_rag()
        elif choice == '5':
            apply_fix_5_reduce_num_queries()
        elif choice == '6':
            restore_backups()
        else:
            print("Invalid choice. Please select 0-6.")
    
    print("\n" + "=" * 80)
    print("Remember to restart your API server for changes to take effect!")
    print("=" * 80)


if __name__ == "__main__":
    main()
