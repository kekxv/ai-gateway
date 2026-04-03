package repository

import (
	"context"
	"testing"
	"time"

	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/test"
	"golang.org/x/crypto/bcrypt"
)

func TestUserRepository_Create(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewUserRepository(db)

	hashedPassword, _ := bcrypt.GenerateFromPassword([]byte("testpassword"), bcrypt.DefaultCost)
	user := &models.User{
		Email:    "create@example.com",
		Password: string(hashedPassword),
		Role:     "USER",
		Balance:  500,
	}

	err := repo.Create(context.Background(), user)
	if err != nil {
		t.Fatalf("Create failed: %v", err)
	}

	if user.ID == 0 {
		t.Error("Expected user ID to be set after creation")
	}
}

func TestUserRepository_FindByID(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewUserRepository(db)

	user := test.CreateTestUser(db, func(u *models.User) {
		u.Email = "findbyid@example.com"
	})

	found, err := repo.FindByID(context.Background(), user.ID)
	if err != nil {
		t.Fatalf("FindByID failed: %v", err)
	}

	if found.Email != "findbyid@example.com" {
		t.Errorf("Expected email 'findbyid@example.com', got '%s'", found.Email)
	}
}

func TestUserRepository_FindByID_NotFound(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewUserRepository(db)

	_, err := repo.FindByID(context.Background(), 999)
	if err == nil {
		t.Error("Expected error for non-existent user ID")
	}
}

func TestUserRepository_FindByEmail(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewUserRepository(db)

	user := test.CreateTestUser(db, func(u *models.User) {
		u.Email = "findbyemail@example.com"
	})

	found, err := repo.FindByEmail(context.Background(), "findbyemail@example.com")
	if err != nil {
		t.Fatalf("FindByEmail failed: %v", err)
	}

	if found.ID != user.ID {
		t.Errorf("Expected user ID %d, got %d", user.ID, found.ID)
	}
}

func TestUserRepository_FindByEmail_NotFound(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewUserRepository(db)

	_, err := repo.FindByEmail(context.Background(), "nonexistent@example.com")
	if err == nil {
		t.Error("Expected error for non-existent email")
	}
}

func TestUserRepository_List(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewUserRepository(db)

	// Create multiple users
	test.CreateTestUser(db, func(u *models.User) {
		u.Email = "user1@example.com"
	})
	test.CreateTestUser(db, func(u *models.User) {
		u.Email = "user2@example.com"
	})
	test.CreateTestUser(db, func(u *models.User) {
		u.Email = "user3@example.com"
	})

	users, err := repo.List(context.Background())
	if err != nil {
		t.Fatalf("List failed: %v", err)
	}

	if len(users) < 3 {
		t.Errorf("Expected at least 3 users, got %d", len(users))
	}
}

func TestUserRepository_Update(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewUserRepository(db)

	user := test.CreateTestUser(db, func(u *models.User) {
		u.Email = "update@example.com"
		u.Balance = 100
	})

	// Update balance
	user.Balance = 500
	err := repo.Update(context.Background(), user)
	if err != nil {
		t.Fatalf("Update failed: %v", err)
	}

	// Verify update
	found, _ := repo.FindByID(context.Background(), user.ID)
	if found.Balance != 500 {
		t.Errorf("Expected balance 500, got %d", found.Balance)
	}
}

func TestUserRepository_Delete(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewUserRepository(db)

	user := test.CreateTestUser(db, func(u *models.User) {
		u.Email = "delete@example.com"
	})

	err := repo.Delete(context.Background(), user.ID)
	if err != nil {
		t.Fatalf("Delete failed: %v", err)
	}

	// Verify deletion
	_, err = repo.FindByID(context.Background(), user.ID)
	if err == nil {
		t.Error("Expected error after user deleted")
	}
}

func TestUserRepository_UpdateBalance(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewUserRepository(db)

	user := test.CreateTestUser(db, func(u *models.User) {
		u.Balance = 100
	})

	// Add 50 to balance
	err := repo.UpdateBalance(context.Background(), user.ID, 50)
	if err != nil {
		t.Fatalf("UpdateBalance failed: %v", err)
	}

	found, _ := repo.FindByID(context.Background(), user.ID)
	if found.Balance != 150 {
		t.Errorf("Expected balance 150, got %d", found.Balance)
	}
}

func TestUserRepository_UpdateBalance_Negative(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewUserRepository(db)

	user := test.CreateTestUser(db, func(u *models.User) {
		u.Balance = 100
	})

	// Subtract from balance (negative amount)
	err := repo.UpdateBalance(context.Background(), user.ID, -30)
	if err != nil {
		t.Fatalf("UpdateBalance failed: %v", err)
	}

	found, _ := repo.FindByID(context.Background(), user.ID)
	if found.Balance != 70 {
		t.Errorf("Expected balance 70, got %d", found.Balance)
	}
}

func TestUserRepository_SubtractBalance(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewUserRepository(db)

	user := test.CreateTestUser(db, func(u *models.User) {
		u.Balance = 100
	})

	err := repo.SubtractBalance(context.Background(), user.ID, 30)
	if err != nil {
		t.Fatalf("SubtractBalance failed: %v", err)
	}

	found, _ := repo.FindByID(context.Background(), user.ID)
	if found.Balance != 70 {
		t.Errorf("Expected balance 70, got %d", found.Balance)
	}
}

func TestUserRepository_Count(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewUserRepository(db)

	// Clear existing data
	test.ClearTables(db, &models.User{})

	// Create users
	test.CreateTestUser(db, func(u *models.User) { u.Email = "count1@example.com" })
	test.CreateTestUser(db, func(u *models.User) { u.Email = "count2@example.com" })

	count, err := repo.Count(context.Background())
	if err != nil {
		t.Fatalf("Count failed: %v", err)
	}

	if count != 2 {
		t.Errorf("Expected count 2, got %d", count)
	}
}

func TestUserRepository_CreateWithValidUntil(t *testing.T) {
	db := test.SetupTestDB(t)
	defer test.CleanupTestDB(db)

	repo := NewUserRepository(db)

	futureTime := time.Now().Add(24 * time.Hour)
	hashedPassword, _ := bcrypt.GenerateFromPassword([]byte("testpassword"), bcrypt.DefaultCost)
	user := &models.User{
		Email:       "expiry@example.com",
		Password:    string(hashedPassword),
		Role:        "USER",
		ValidUntil:  &futureTime,
	}

	err := repo.Create(context.Background(), user)
	if err != nil {
		t.Fatalf("Create failed: %v", err)
	}

	found, _ := repo.FindByID(context.Background(), user.ID)
	if found.ValidUntil == nil {
		t.Error("Expected ValidUntil to be set")
	}
}